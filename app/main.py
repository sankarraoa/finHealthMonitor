"""FastAPI application for Xero Chart of Accounts."""
from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import secrets
from typing import Optional, Dict, Any, List
import logging
import asyncio
import re
from datetime import datetime, timedelta
import uuid

from app.config import config
from app.xero_client import XeroClient
from app.mcp_client import XeroMCPClient
from app.agents.payroll_risk_agent import PayrollRiskAgent
from app.connections import connection_manager
from app.quickbooks_client import QuickBooksClient
from app.payroll_risk_db import payroll_risk_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="FinHealthMonitor", description="Xero Chart of Accounts Viewer")

# Add session middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    session_cookie=config.SESSION_COOKIE_NAME,
    max_age=3600 * 24  # 24 hours
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="app/templates")

# Add JSON filter for templates
import json
def tojson_filter(obj):
    """Convert object to JSON string (single-line for JavaScript compatibility)."""
    return json.dumps(obj, separators=(',', ':'), default=str)

templates.env.filters["tojson"] = tojson_filter

# Initialize Xero client
xero_client = XeroClient()


def get_connections_for_selector() -> Dict[str, Any]:
    """
    Get all active connections grouped by category for the connection selector widget.
    Groups Xero connections by refresh_token (one per OAuth authorization).
    Returns connections and categories info.
    """
    all_connections = connection_manager.get_all_connections()
    
    # Filter active connections (with access_token)
    active_connections = []
    for conn in all_connections:
        if conn.get("access_token"):
            # Ensure tenants array is set for Xero
            if conn.get("software") == "xero":
                tenants = connection_manager.get_all_tenants_for_connection(conn["id"])
                conn["tenants"] = tenants if tenants else []
            active_connections.append(conn)
    
    # Group Xero connections by refresh_token (one per OAuth authorization)
    grouped_connections = []
    xero_refresh_tokens_seen = set()
    
    for conn in active_connections:
        if conn.get("software") == "xero":
            refresh_token = conn.get("refresh_token")
            if refresh_token and refresh_token in xero_refresh_tokens_seen:
                continue  # Skip duplicate OAuth authorization
            if refresh_token:
                xero_refresh_tokens_seen.add(refresh_token)
        grouped_connections.append(conn)
    
    # Sort by created_at
    grouped_connections.sort(key=lambda x: x.get("created_at", ""))
    
    # Get category info
    categories = {}
    for category_key, category_info in connection_manager.SOFTWARE_CATEGORIES.items():
        categories[category_key] = {
            "name": category_info["name"],
            "software": category_info["software"]
        }
    
    return {
        "connections": grouped_connections,
        "categories": categories
    }


async def get_selected_connection_and_tenant(
    request: Request,
    software_filter: Optional[str] = None,
    require_tenant: bool = False
) -> Dict[str, Any]:
    """
    Helper function to get selected connection and tenant for a page.
    
    Args:
        request: FastAPI request object
        software_filter: Optional filter by software type (e.g., "xero")
        require_tenant: If True, requires tenant selection (for connections like Xero)
    
    Returns:
        Dict with:
            - selected_connection: The selected connection object
            - selected_tenant: The selected tenant object (None if not applicable)
            - access_token: Access token for API calls
            - tenant_id: Tenant ID (None if not applicable)
            - tenant_name: Tenant name (None if not applicable)
            - error: Error message if any
            - selector_data: Connection selector data for template
    """
    connection_id = request.query_params.get("connection_id")
    tenant_id = request.query_params.get("tenant_id")
    
    # Get all active connections
    if software_filter:
        all_active_connections = connection_manager.get_active_connections(software=software_filter)
    else:
        all_active_connections = connection_manager.get_active_connections()
    
    selector_data = get_connections_for_selector()
    
    if not all_active_connections:
        return {
            "selected_connection": None,
            "selected_tenant": None,
            "access_token": None,
            "tenant_id": None,
            "tenant_name": None,
            "error": "No active connections found. Please connect an account in Settings.",
            "selector_data": selector_data
        }
    
    # Group Xero connections by refresh_token (one connection per OAuth authorization)
    active_connections = []
    xero_refresh_tokens_seen = set()
    
    for conn in all_active_connections:
        if conn.get("software") == "xero":
            refresh_token = conn.get("refresh_token")
            if refresh_token and refresh_token in xero_refresh_tokens_seen:
                continue
            if refresh_token:
                xero_refresh_tokens_seen.add(refresh_token)
        active_connections.append(conn)
    
    # Sort by created_at to get oldest first (default)
    active_connections.sort(key=lambda x: x.get("created_at", ""))
    
    # Get selected connection
    selected_connection = None
    if connection_id:
        selected_connection = next(
            (c for c in active_connections if c["id"] == connection_id),
            None
        )
    
    # Default to first connection if no selection or invalid selection
    if not selected_connection:
        selected_connection = active_connections[0]
    
    # Refresh token if expired
    if connection_manager.is_token_expired(selected_connection["id"]):
        refresh_token = selected_connection.get("refresh_token")
        if refresh_token:
            try:
                # Run token refresh in thread pool to avoid blocking async event loop
                import asyncio
                token_response = await asyncio.to_thread(xero_client.refresh_token, refresh_token)
                connection_manager.sync_tokens_for_refresh_token(
                    refresh_token=refresh_token,
                    new_access_token=token_response.get("access_token"),
                    new_refresh_token=token_response.get("refresh_token", refresh_token),
                    expires_in=token_response.get("expires_in", 1800),
                    software="xero"
                )
                selected_connection = connection_manager.get_connection(selected_connection["id"])
                logger.info(f"Successfully refreshed token for connection {selected_connection['id']}")
            except Exception as refresh_error:
                logger.error(f"Failed to refresh token: {str(refresh_error)}", exc_info=True)
                return {
                    "selected_connection": selected_connection,
                    "selected_tenant": None,
                    "access_token": None,
                    "tenant_id": None,
                    "tenant_name": None,
                    "error": f"Connection '{selected_connection.get('name')}' has expired and could not be refreshed. Please refresh manually in Settings.",
                    "selector_data": selector_data
                }
        else:
            return {
                "selected_connection": selected_connection,
                "selected_tenant": None,
                "access_token": None,
                "tenant_id": None,
                "tenant_name": None,
                "error": f"Connection '{selected_connection.get('name')}' has expired and cannot be refreshed. Please reconnect in Settings.",
                "selector_data": selector_data
            }
    
    access_token = selected_connection.get("access_token")
    
    # Handle tenant selection for connections that support tenants (like Xero)
    selected_tenant = None
    tenant_id_result = None
    tenant_name_result = None
    
    # Check if this connection type supports tenants
    supports_tenants = selected_connection.get("software") == "xero"  # Add other software types as needed
    
    if supports_tenants or require_tenant:
        tenants = connection_manager.get_all_tenants_for_connection(selected_connection["id"])
        
        if not tenants:
            return {
                "selected_connection": selected_connection,
                "selected_tenant": None,
                "access_token": access_token,
                "tenant_id": None,
                "tenant_name": None,
                "error": f"Connection '{selected_connection.get('name')}' has no tenants. Please reconnect in Settings.",
                "selector_data": selector_data
            }
        
        # Get selected tenant
        if tenant_id:
            selected_tenant = next(
                (t for t in tenants if t.get("tenant_id") == tenant_id),
                None
            )
        
        # Default to first tenant if no selection or invalid selection
        if not selected_tenant:
            selected_tenant = tenants[0]
        
        tenant_id_result = selected_tenant.get("tenant_id")
        tenant_name_result = selected_tenant.get("tenant_name", "Unknown")
    
    return {
        "selected_connection": selected_connection,
        "selected_tenant": selected_tenant,
        "access_token": access_token,
        "tenant_id": tenant_id_result,
        "tenant_name": tenant_name_result,
        "error": None,
        "selector_data": selector_data
    }

# Progress tracking for async operations
# Store progress by session ID: {session_id: {"status": "loading|complete|error", "progress": 0-100, "message": "...", "data": {...}}}
_invoice_progress: Dict[str, Dict[str, Any]] = {}
_account_progress: Dict[str, Dict[str, Any]] = {}
_journal_progress: Dict[str, Dict[str, Any]] = {}
_transaction_progress: Dict[str, Dict[str, Any]] = {}
_payroll_risk_progress: Dict[str, Dict[str, Any]] = {}

async def _run_payroll_risk_async(
    analysis_id: str,
    connection_id: str,
    connection_name: str,
    tenant_id: Optional[str],
    tenant_name: Optional[str],
    access_token: str,
    llm_model: Optional[str] = None
):
    """Background task to run payroll risk analysis with progress tracking and database storage."""
    progress_key = f"payroll_risk_progress_{analysis_id}"
    
    try:
        # Initialize progress in memory (for real-time updates)
        _payroll_risk_progress[progress_key] = {
            "status": "loading",
            "progress": 0,
            "message": "🚀 Starting payroll risk analysis...",
            "data": None,
            "error": None
        }
        
        def update_progress(progress: int, message: str):
            """Update progress callback - updates both memory and database."""
            if progress_key in _payroll_risk_progress:
                _payroll_risk_progress[progress_key]["progress"] = progress
                _payroll_risk_progress[progress_key]["message"] = message
            
            # Also update database
            payroll_risk_db.update_progress(analysis_id, progress, message)
        
        # Create agent with progress callback
        agent = PayrollRiskAgent(
            bearer_token=access_token,
            llm_model=llm_model,
            progress_callback=update_progress
        )
        
        # Run analysis
        result = await agent.run()
        
        # Convert result to dict for storage
        if hasattr(result, 'to_dict'):
            result_dict = result.to_dict()
        else:
            result_dict = result if isinstance(result, dict) else {"raw_result": str(result)}
        
        # Store in database
        payroll_risk_db.complete_analysis(analysis_id, result_dict)
        
        # Mark as complete in memory
        _payroll_risk_progress[progress_key] = {
            "status": "complete",
            "progress": 100,
            "message": "✅ Analysis complete!",
            "data": result_dict,
            "error": None
        }
        
        logger.info(f"Payroll risk analysis {analysis_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Error in payroll risk analysis {analysis_id}: {str(e)}", exc_info=True)
        
        # Store error in database
        payroll_risk_db.fail_analysis(analysis_id, str(e))
        
        # Mark as error in memory
        _payroll_risk_progress[progress_key] = {
            "status": "error",
            "progress": 0,
            "message": "Error occurred",
            "data": None,
            "error": str(e)
        }


def is_authenticated(request: Request) -> bool:
    """Check if user is authenticated."""
    return "access_token" in request.session and "tenant_id" in request.session


def is_token_expired(request: Request) -> bool:
    """Check if the access token has expired."""
    if "access_token" not in request.session:
        return True
    
    # Check if we have expiration info
    expires_in = request.session.get("expires_in")
    token_created_at = request.session.get("token_created_at")
    
    if not expires_in or not token_created_at:
        # If we don't have expiration info, assume it might be expired
        # Try to refresh or re-authenticate
        return True
    
    # Calculate expiration time
    try:
        created_time = datetime.fromisoformat(token_created_at)
        expiration_time = created_time + timedelta(seconds=expires_in)
        # Add 60 second buffer to refresh before actual expiration
        return datetime.now() >= (expiration_time - timedelta(seconds=60))
    except (ValueError, TypeError):
        # If we can't parse the date, assume expired
        return True


def check_and_refresh_token(request: Request) -> bool:
    """
    Check if token is expired and try to refresh it.
    Returns True if token is valid (or was successfully refreshed), False otherwise.
    """
    if not is_authenticated(request):
        return False
    
    if not is_token_expired(request):
        return True
    
    # Token is expired, try to refresh
    refresh_token = request.session.get("refresh_token")
    if not refresh_token:
        logger.warning("Token expired and no refresh token available")
        return False
    
    try:
        logger.info("Token expired, attempting to refresh...")
        token_response = xero_client.refresh_token(refresh_token)
        
        # Update session with new tokens
        request.session["access_token"] = token_response.get("access_token")
        request.session["refresh_token"] = token_response.get("refresh_token")
        request.session["expires_in"] = token_response.get("expires_in", 1800)
        request.session["token_created_at"] = datetime.now().isoformat()
        
        logger.info("Token successfully refreshed")
        return True
    except Exception as e:
        logger.error(f"Token refresh failed: {str(e)}")
        # Clear session on refresh failure
        clear_xero_session(request)
        return False


def clear_xero_session(request: Request):
    """Clear all Xero-related session data."""
    request.session.pop("access_token", None)
    request.session.pop("refresh_token", None)
    request.session.pop("tenant_id", None)
    request.session.pop("tenant_name", None)
    request.session.pop("expires_in", None)
    request.session.pop("token_created_at", None)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root endpoint - redirects to home page."""
    return RedirectResponse(url="/home")


@app.get("/debug/xero-config")
async def debug_xero_config(request: Request):
    """Debug endpoint to check Xero configuration."""
    return JSONResponse({
        "client_id_set": bool(xero_client.client_id),
        "client_id_length": len(xero_client.client_id) if xero_client.client_id else 0,
        "client_id_preview": xero_client.client_id[:10] + "..." if xero_client.client_id and len(xero_client.client_id) > 10 else (xero_client.client_id or "NOT SET"),
        "redirect_uri": xero_client.redirect_uri,
        "auth_url": xero_client.auth_url,
        "scopes": xero_client.scopes
    })


@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    """Initiate Xero OAuth login flow."""
    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    
    # Get authorization URL
    auth_url = xero_client.get_authorization_url(state=state)
    
    logger.info("Redirecting to Xero authorization")
    return RedirectResponse(url=auth_url)


@app.get("/callback")
async def callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Handle OAuth callback (legacy route - redirects to new route for multi-tenant support)."""
    logger.info(f"=== OAUTH CALLBACK RECEIVED (LEGACY ROUTE - REDIRECTING) ===")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request URL: {request.url}")
    logger.info(f"Code parameter: {'present' if code else 'missing'}")
    logger.info(f"State parameter: {state}")
    logger.info(f"Error parameter: {error}")
    logger.info(f"Session keys: {list(request.session.keys())}")
    
    # Determine software type from session or default to xero
    software = request.session.get("pending_software", "xero")
    logger.info(f"Redirecting to /callback/{software}")
    
    # Redirect to new callback route with all query parameters
    query_params = dict(request.query_params)
    if query_params:
        from urllib.parse import urlencode
        query_string = urlencode(query_params)
        redirect_url = f"/callback/{software}?{query_string}"
    else:
        redirect_url = f"/callback/{software}"
    
    logger.info(f"Redirecting to: {redirect_url}")
    return RedirectResponse(url=redirect_url, status_code=303)


@app.get("/accounts", response_class=HTMLResponse)
async def accounts(request: Request, connection_id: Optional[str] = None):
    """Display chart of accounts with connection selection."""
    try:
        # Get selected connection and tenant using helper function
        selection = await get_selected_connection_and_tenant(
            request,
            software_filter="xero",
            require_tenant=True
        )
        
        if selection["error"]:
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "error": selection["error"],
                    "connections": selection["selector_data"]["connections"],
                    "categories": selection["selector_data"]["categories"],
                    "selected_connection_ids": [selection["selected_connection"]["id"]] if selection["selected_connection"] else [],
                    "allow_multiple": False,
                    "selected_connection": selection["selected_connection"],
                    "selected_tenant": selection["selected_tenant"],
                    "accounts": [],
                    "account_count": 0
                }
            )
        
        selected_connection = selection["selected_connection"]
        selected_tenant = selection["selected_tenant"]
        access_token = selection["access_token"]
        tenant_id = selection["tenant_id"]
        tenant_name = selection["tenant_name"]
        
        # Check if connection is Xero
        if selected_connection.get("software") != "xero":
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "error": f"Chart of Accounts is only available for Xero connections. Selected connection '{selected_connection.get('name')}' is a {selected_connection.get('software', 'unknown')} connection.",
                    "connections": selection["selector_data"]["connections"],
                    "categories": selection["selector_data"]["categories"],
                    "selected_connection_ids": [selected_connection["id"]],
                    "allow_multiple": False,
                    "selected_connection": selected_connection,
                    "selected_tenant": selected_tenant,
                    "accounts": [],
                    "account_count": 0
                }
            )
        
        # Check if async mode is requested
        async_param = request.query_params.get("async", "true")
        use_async = async_param.lower() == "true"
        
        if use_async:
            # Generate a unique session ID for progress tracking
            session_id = request.session.get("session_id")
            if not session_id:
                session_id = str(uuid.uuid4())
                request.session["session_id"] = session_id
            
            progress_key = f"account_progress_{session_id}"
            
            # Check if there's already a result
            if progress_key in _account_progress:
                progress_data = _account_progress[progress_key]
                if progress_data["status"] == "complete" and progress_data["data"]:
                    result_data = progress_data["data"]
                    del _account_progress[progress_key]
                    return templates.TemplateResponse(
                        "index.html",
                        {
                            "request": request,
                            "connections": selection["selector_data"]["connections"],
                            "categories": selection["selector_data"]["categories"],
                            "selected_connection_ids": [selected_connection["id"]],
                            "allow_multiple": False,
                            "selected_connection": selected_connection,
                            "selected_tenant": selected_tenant,
                            "accounts": result_data["accounts"],
                            "account_count": result_data["account_count"],
                            "async_mode": False
                        }
                    )
                elif progress_data["status"] == "error":
                    error_msg = progress_data.get("error", "Unknown error")
                    del _account_progress[progress_key]
                    return templates.TemplateResponse(
                        "index.html",
                        {
                            "request": request,
                            "error": f"Failed to fetch accounts: {error_msg}",
                            "connections": selection["selector_data"]["connections"],
                            "categories": selection["selector_data"]["categories"],
                            "selected_connection_ids": [selected_connection["id"]],
                            "allow_multiple": False,
                            "selected_connection": selected_connection,
                            "selected_tenant": selected_tenant,
                            "accounts": [],
                            "account_count": 0,
                            "async_mode": False
                        }
                    )
            
            # Start background task if not already running
            if progress_key not in _account_progress or _account_progress[progress_key]["status"] != "loading":
                asyncio.create_task(_fetch_accounts_async(session_id, access_token, tenant_id))
            
            # Return loading page
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "connections": selection["selector_data"]["connections"],
                    "categories": selection["selector_data"]["categories"],
                    "selected_connection_ids": [selected_connection["id"]],
                    "allow_multiple": False,
                    "selected_connection": selected_connection,
                    "selected_tenant": selected_tenant,
                    "accounts": None,
                    "account_count": 0,
                    "async_mode": True,
                    "session_id": session_id
                }
            )
        
        # Synchronous mode
        accounts_data = xero_client.get_accounts(access_token, tenant_id)
        accounts_list = accounts_data.get("Accounts", [])
        accounts_list.sort(key=lambda x: x.get("Code", ""))
        
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "connections": selection["selector_data"]["connections"],
                "categories": selection["selector_data"]["categories"],
                "selected_connection_ids": [selected_connection["id"]],
                "allow_multiple": False,
                "selected_connection": selected_connection,
                "selected_tenant": selected_tenant,
                "accounts": accounts_list,
                "account_count": len(accounts_list),
                "async_mode": False
            }
        )
    
    except Exception as e:
        logger.error(f"Error fetching accounts: {str(e)}")
        selector_data = get_connections_for_selector()
        selected_connection_id = selection["selected_connection"]["id"] if 'selection' in locals() and selection["selected_connection"] else None
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": f"Error fetching accounts: {str(e)}",
                "connections": selector_data["connections"],
                "categories": selector_data["categories"],
                "selected_connection_ids": [selected_connection_id] if selected_connection_id else [],
                "allow_multiple": False,
                "selected_connection": selection["selected_connection"] if 'selection' in locals() and selection["selected_connection"] else None,
                "selected_tenant": selection["selected_tenant"] if 'selection' in locals() and selection["selected_tenant"] else None,
                "accounts": [],
                "account_count": 0
            }
        )


async def _fetch_invoices_async(session_id: str, access_token: str):
    """Background task to fetch invoices with progress tracking."""
    progress_key = f"invoice_progress_{session_id}"
    
    try:
        # Initialize progress
        _invoice_progress[progress_key] = {
            "status": "loading",
            "progress": 0,
            "message": "Initializing...",
            "data": None,
            "error": None
        }
        
        def update_progress(progress: int, message: str):
            """Update progress callback."""
            if progress_key in _invoice_progress:
                _invoice_progress[progress_key]["progress"] = progress
                _invoice_progress[progress_key]["message"] = message
        
        mcp_client = None
        try:
            # Create MCP client with bearer token
            update_progress(5, "Connecting to Xero...")
            mcp_client = XeroMCPClient(bearer_token=access_token)
            
            # Fetch outstanding invoices via MCP with timeout
            update_progress(10, "Fetching invoices from Xero...")
            invoices_list = await asyncio.wait_for(
                mcp_client.get_outstanding_invoices(progress_callback=update_progress),
                timeout=60.0  # 60 second timeout
            )
            
            # Close MCP client
            await mcp_client.close()
            mcp_client = None
            
            # Calculate totals
            update_progress(99, "Calculating totals...")
            total_outstanding = sum(
                float(inv.get("AmountDue", 0) or 0) 
                for inv in invoices_list
            )
            
            # Mark as complete
            _invoice_progress[progress_key] = {
                "status": "complete",
                "progress": 100,
                "message": "Complete",
                "data": {
                    "invoices": invoices_list,
                    "invoice_count": len(invoices_list),
                    "total_outstanding": total_outstanding
                },
                "error": None
            }
            
        except Exception as e:
            logger.error(f"Error fetching invoices: {str(e)}", exc_info=True)
            if mcp_client:
                try:
                    await mcp_client.close()
                except:
                    pass
            
            _invoice_progress[progress_key] = {
                "status": "error",
                "progress": 0,
                "message": "Error occurred",
                "data": None,
                "error": str(e)
            }
    except Exception as e:
        logger.error(f"Error in background task: {str(e)}", exc_info=True)
        if progress_key in _invoice_progress:
            _invoice_progress[progress_key]["status"] = "error"
            _invoice_progress[progress_key]["error"] = str(e)


@app.get("/invoices", response_class=HTMLResponse)
async def invoices(request: Request, async_mode: bool = False):
    """Display outstanding invoices using MCP server."""
    logger.info(f"Invoices endpoint called (async_mode={async_mode})")
    
    try:
        # Get selected connection and tenant using helper function
        selection = await get_selected_connection_and_tenant(
            request,
            software_filter="xero",
            require_tenant=True
        )
        
        if selection["error"]:
            return templates.TemplateResponse(
                "invoices.html",
                {
                    "request": request,
                    "error": selection["error"],
                    "connections": selection["selector_data"]["connections"],
                    "categories": selection["selector_data"]["categories"],
                    "selected_connection_ids": [selection["selected_connection"]["id"]] if selection["selected_connection"] else [],
                    "allow_multiple": False,
                    "selected_connection": selection["selected_connection"],
                    "selected_tenant": selection["selected_tenant"],
                    "invoices": [],
                    "invoice_count": 0,
                    "total_outstanding": 0
                }
            )
        
        selected_connection = selection["selected_connection"]
        selected_tenant = selection["selected_tenant"]
        access_token = selection["access_token"]
        tenant_id = selection["tenant_id"]
        tenant_name = selection["tenant_name"]
        
        # Check if async mode is requested or if we should use it by default
        # Default to async mode unless explicitly disabled
        async_param = request.query_params.get("async", "true")
        use_async = async_mode if async_mode else (async_param.lower() == "true")
        
        if use_async:
            # Generate a unique session ID for progress tracking
            session_id = request.session.get("session_id")
            if not session_id:
                session_id = str(uuid.uuid4())
                request.session["session_id"] = session_id
            
            progress_key = f"invoice_progress_{session_id}"
            
            # Check if there's already a result
            if progress_key in _invoice_progress:
                progress_data = _invoice_progress[progress_key]
                if progress_data["status"] == "complete" and progress_data["data"]:
                    # Clear the progress and return the result
                    result_data = progress_data["data"]
                    del _invoice_progress[progress_key]
                    return templates.TemplateResponse(
                        "invoices.html",
                        {
                            "request": request,
                            "invoices": result_data["invoices"],
                            "invoice_count": result_data["invoice_count"],
                            "total_outstanding": result_data["total_outstanding"],
                            "async_mode": True,
                            "connections": selection["selector_data"]["connections"],
                            "categories": selection["selector_data"]["categories"],
                            "selected_connection_ids": [selected_connection["id"]],
                            "allow_multiple": False,
                            "selected_connection": selected_connection,
                            "selected_tenant": selected_tenant
                        }
                    )
                elif progress_data["status"] == "error":
                    error_msg = progress_data.get("error", "Unknown error")
                    del _invoice_progress[progress_key]
                    return templates.TemplateResponse(
                        "invoices.html",
                        {
                            "request": request,
                            "error": f"Failed to fetch invoices: {error_msg}",
                            "invoices": [],
                            "invoice_count": 0,
                            "total_outstanding": 0,
                            "async_mode": True,
                            "connections": selection["selector_data"]["connections"],
                            "categories": selection["selector_data"]["categories"],
                            "selected_connection_ids": [selected_connection["id"]],
                            "allow_multiple": False,
                            "selected_connection": selected_connection,
                            "selected_tenant": selected_tenant
                        }
                    )
            
            # Start background task if not already running
            if progress_key not in _invoice_progress or _invoice_progress[progress_key]["status"] != "loading":
                # Start background task
                asyncio.create_task(_fetch_invoices_async(session_id, access_token))
            
            # Return loading page
            return templates.TemplateResponse(
                "invoices.html",
                {
                    "request": request,
                    "invoices": None,
                    "invoice_count": 0,
                    "total_outstanding": 0,
                    "async_mode": True,
                    "session_id": session_id,
                    "connections": selection["selector_data"]["connections"],
                    "categories": selection["selector_data"]["categories"],
                    "selected_connection_ids": [selected_connection["id"]],
                    "allow_multiple": False,
                    "selected_connection": selected_connection,
                    "selected_tenant": selected_tenant
                }
            )
        else:
            # Synchronous mode (original behavior)
            logger.info(f"Fetching invoices for tenant: {tenant_name} (ID: {tenant_id})")
            
            mcp_client = None
            try:
                # Create MCP client with bearer token
                logger.info("Initializing MCP client...")
                mcp_client = XeroMCPClient(bearer_token=access_token)
                logger.info(f"MCP client created, server path: {mcp_client.mcp_server_path}")
                
                # Fetch outstanding invoices via MCP with timeout
                logger.info("Fetching outstanding invoices from MCP server...")
                try:
                    invoices_list = await asyncio.wait_for(
                        mcp_client.get_outstanding_invoices(),
                        timeout=30.0  # 30 second timeout
                    )
                    logger.info(f"Successfully fetched {len(invoices_list)} invoices from MCP server")
                except asyncio.TimeoutError:
                    logger.error("MCP server request timed out after 30 seconds")
                    raise Exception("Request timed out. The MCP server may not be responding. Please check the server logs.")
                except Exception as mcp_error:
                    logger.error(f"MCP server error: {str(mcp_error)}", exc_info=True)
                    raise
                
                # Close MCP client
                logger.info("Closing MCP client connection...")
                await mcp_client.close()
                mcp_client = None
                
                # Calculate totals
                logger.info("Calculating invoice totals...")
                total_outstanding = sum(
                    float(inv.get("AmountDue", 0) or 0) 
                    for inv in invoices_list
                )
                logger.info(f"Total outstanding amount: ${total_outstanding:.2f}")
                
                logger.info(f"Rendering invoices page with {len(invoices_list)} invoices")
                return templates.TemplateResponse(
                    "invoices.html",
                    {
                        "request": request,
                        "invoices": invoices_list,
                        "invoice_count": len(invoices_list),
                        "total_outstanding": total_outstanding,
                        "async_mode": False,
                        "connections": selection["selector_data"]["connections"],
                        "categories": selection["selector_data"]["categories"],
                        "selected_connection_ids": [selected_connection["id"]],
                        "allow_multiple": False,
                        "selected_connection": selected_connection,
                        "selected_tenant": selected_tenant
                    }
                )
            
            except Exception as mcp_e:
                logger.error(f"Error fetching invoices via MCP: {str(mcp_e)}", exc_info=True)
                
                # Ensure MCP client is closed even on error
                if mcp_client:
                    try:
                        logger.info("Attempting to close MCP client after error...")
                        await mcp_client.close()
                    except Exception as close_error:
                        logger.error(f"Error closing MCP client: {str(close_error)}")
                
                return templates.TemplateResponse(
                    "invoices.html",
                    {
                        "request": request,
                        "error": f"Failed to fetch invoices: {str(mcp_e)}",
                        "invoices": [],
                        "invoice_count": 0,
                        "total_outstanding": 0,
                        "async_mode": False,
                        "connections": selection["selector_data"]["connections"],
                        "categories": selection["selector_data"]["categories"],
                        "selected_connection_ids": [selected_connection["id"]],
                        "allow_multiple": False,
                        "selected_connection": selected_connection,
                        "selected_tenant": selected_tenant
                    }
                )
    
    except Exception as e:
        logger.error(f"Error in invoices route: {str(e)}", exc_info=True)
        selector_data = get_connections_for_selector()
        selected_connection_id = selection["selected_connection"]["id"] if 'selection' in locals() and selection["selected_connection"] else None
        return templates.TemplateResponse(
            "invoices.html",
            {
                "request": request,
                "error": f"Failed to load invoices: {str(e)}",
                "invoices": [],
                "invoice_count": 0,
                "total_outstanding": 0,
                "async_mode": False,
                "connections": selector_data["connections"],
                "categories": selector_data["categories"],
                "selected_connection_ids": [selected_connection_id] if selected_connection_id else [],
                "allow_multiple": False,
                "selected_connection": selection["selected_connection"] if 'selection' in locals() and selection["selected_connection"] else None,
                "selected_tenant": selection["selected_tenant"] if 'selection' in locals() and selection["selected_tenant"] else None
            }
        )


@app.get("/invoices/progress")
async def invoices_progress(request: Request):
    """Get progress status for invoice fetching."""
    session_id = request.session.get("session_id")
    if not session_id:
        return JSONResponse({"status": "error", "message": "No session ID"})
    
    progress_key = f"invoice_progress_{session_id}"
    
    if progress_key not in _invoice_progress:
        return JSONResponse({
            "status": "not_started",
            "progress": 0,
            "message": "Not started"
        })
    
    progress_data = _invoice_progress[progress_key]
    return JSONResponse({
        "status": progress_data["status"],
        "progress": progress_data["progress"],
        "message": progress_data["message"],
        "error": progress_data.get("error")
    })


async def _fetch_accounts_async(session_id: str, access_token: str, tenant_id: str):
    """Background task to fetch accounts with progress tracking."""
    progress_key = f"account_progress_{session_id}"
    
    try:
        _account_progress[progress_key] = {
            "status": "loading",
            "progress": 0,
            "message": "Initializing...",
            "data": None,
            "error": None
        }
        
        def update_progress(progress: int, message: str):
            if progress_key in _account_progress:
                _account_progress[progress_key]["progress"] = progress
                _account_progress[progress_key]["message"] = message
        
        update_progress(10, "Connecting to Xero...")
        xero_client_instance = XeroClient()
        
        update_progress(30, "Fetching accounts...")
        accounts_data = xero_client_instance.get_accounts(access_token, tenant_id)
        accounts_list = accounts_data.get("Accounts", [])
        accounts_list.sort(key=lambda x: x.get("Code", ""))
        
        update_progress(100, "Complete")
        _account_progress[progress_key] = {
            "status": "complete",
            "progress": 100,
            "message": "Complete",
            "data": {"accounts": accounts_list, "account_count": len(accounts_list)},
            "error": None
        }
    except Exception as e:
        logger.error(f"Error fetching accounts: {str(e)}", exc_info=True)
        _account_progress[progress_key] = {
            "status": "error",
            "progress": 0,
            "message": "Error occurred",
            "data": None,
            "error": str(e)
        }


async def _fetch_journals_async(session_id: str, access_token: str, tenant_id: str):
    """Background task to fetch manual journals with progress tracking."""
    progress_key = f"journal_progress_{session_id}"
    mcp_client = None
    
    try:
        _journal_progress[progress_key] = {
            "status": "loading",
            "progress": 0,
            "message": "Initializing...",
            "data": None,
            "error": None
        }
        
        def update_progress(progress: int, message: str):
            if progress_key in _journal_progress:
                _journal_progress[progress_key]["progress"] = progress
                _journal_progress[progress_key]["message"] = message
        
        update_progress(10, "Connecting to Xero...")
        mcp_client = XeroMCPClient(bearer_token=access_token)
        
        update_progress(30, "Fetching manual journals...")
        result = await mcp_client.call_tool("list-manual-journals", {})
        
        parsed_journals = []
        if isinstance(result, dict) and "content" in result:
            update_progress(50, "Processing journals...")
            journals = await _process_manual_journals_content(
                result["content"], 
                mcp_client,
                access_token=access_token,
                tenant_id=tenant_id
            )
            
            update_progress(80, "Parsing journal data...")
            for item in journals:
                if item.get("type") == "text":
                    parsed_journal = _parse_manual_journal_text(item.get("text", ""))
                    parsed_journals.append(parsed_journal)
        
        await mcp_client.close()
        mcp_client = None
        
        update_progress(100, "Complete")
        _journal_progress[progress_key] = {
            "status": "complete",
            "progress": 100,
            "message": "Complete",
            "data": {"journals": parsed_journals},
            "error": None
        }
    except Exception as e:
        logger.error(f"Error fetching journals: {str(e)}", exc_info=True)
        if mcp_client:
            try:
                await mcp_client.close()
            except:
                pass
        _journal_progress[progress_key] = {
            "status": "error",
            "progress": 0,
            "message": "Error occurred",
            "data": None,
            "error": str(e)
        }


async def _fetch_transactions_async(session_id: str, access_token: str):
    """Background task to fetch bank transactions with progress tracking."""
    progress_key = f"transaction_progress_{session_id}"
    mcp_client = None
    
    try:
        _transaction_progress[progress_key] = {
            "status": "loading",
            "progress": 0,
            "message": "Initializing...",
            "data": None,
            "error": None
        }
        
        def update_progress(progress: int, message: str):
            if progress_key in _transaction_progress:
                _transaction_progress[progress_key]["progress"] = progress
                _transaction_progress[progress_key]["message"] = message
        
        update_progress(10, "Connecting to Xero...")
        mcp_client = XeroMCPClient(bearer_token=access_token)
        
        update_progress(30, "Fetching bank transactions...")
        result = await mcp_client.call_tool("list-bank-transactions", {"page": 1})
        
        parsed_transactions = []
        if isinstance(result, dict) and "content" in result:
            update_progress(60, "Processing transactions...")
            transactions = result["content"]
            
            update_progress(80, "Parsing transaction data...")
            for item in transactions:
                if item.get("type") == "text":
                    parsed_transaction = _parse_bank_transaction_text(item.get("text", ""))
                    parsed_transactions.append(parsed_transaction)
        
        await mcp_client.close()
        mcp_client = None
        
        update_progress(100, "Complete")
        _transaction_progress[progress_key] = {
            "status": "complete",
            "progress": 100,
            "message": "Complete",
            "data": {"transactions": parsed_transactions},
            "error": None
        }
    except Exception as e:
        logger.error(f"Error fetching transactions: {str(e)}", exc_info=True)
        if mcp_client:
            try:
                await mcp_client.close()
            except:
                pass
        _transaction_progress[progress_key] = {
            "status": "error",
            "progress": 0,
            "message": "Error occurred",
            "data": None,
            "error": str(e)
        }


@app.get("/accounts/progress")
async def accounts_progress(request: Request):
    """Get progress status for accounts fetching."""
    session_id = request.session.get("session_id")
    if not session_id:
        return JSONResponse({"status": "error", "message": "No session ID"})
    
    progress_key = f"account_progress_{session_id}"
    
    if progress_key not in _account_progress:
        return JSONResponse({
            "status": "not_started",
            "progress": 0,
            "message": "Not started"
        })
    
    progress_data = _account_progress[progress_key]
    return JSONResponse({
        "status": progress_data["status"],
        "progress": progress_data["progress"],
        "message": progress_data["message"],
        "error": progress_data.get("error")
    })


@app.get("/manual-journals/progress")
async def journals_progress(request: Request):
    """Get progress status for manual journals fetching."""
    session_id = request.session.get("session_id")
    if not session_id:
        return JSONResponse({"status": "error", "message": "No session ID"})
    
    progress_key = f"journal_progress_{session_id}"
    
    if progress_key not in _journal_progress:
        return JSONResponse({
            "status": "not_started",
            "progress": 0,
            "message": "Not started"
        })
    
    progress_data = _journal_progress[progress_key]
    return JSONResponse({
        "status": progress_data["status"],
        "progress": progress_data["progress"],
        "message": progress_data["message"],
        "error": progress_data.get("error")
    })


@app.get("/bank-transactions/progress")
async def transactions_progress(request: Request):
    """Get progress status for bank transactions fetching."""
    session_id = request.session.get("session_id")
    if not session_id:
        return JSONResponse({"status": "error", "message": "No session ID"})
    
    progress_key = f"transaction_progress_{session_id}"
    
    if progress_key not in _transaction_progress:
        return JSONResponse({
            "status": "not_started",
            "progress": 0,
            "message": "Not started"
        })
    
    progress_data = _transaction_progress[progress_key]
    return JSONResponse({
        "status": progress_data["status"],
        "progress": progress_data["progress"],
        "message": progress_data["message"],
        "error": progress_data.get("error")
    })


@app.get("/home", response_class=HTMLResponse)
async def home(request: Request):
    """Display home page."""
    # Get connections for selector
    selector_data = get_connections_for_selector()
    
    # Get selected connection IDs from query params
    connection_ids_param = request.query_params.get("connection_ids", "")
    selected_connection_ids = [cid.strip() for cid in connection_ids_param.split(",") if cid.strip()] if connection_ids_param else []
    connection_id_param = request.query_params.get("connection_id")
    if connection_id_param and connection_id_param not in selected_connection_ids:
        selected_connection_ids.append(connection_id_param)
    
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "connections": selector_data["connections"],
            "categories": selector_data["categories"],
            "selected_connection_ids": selected_connection_ids,
            "allow_multiple": False
        }
    )


async def _check_xero_connection_exists(connection: Dict[str, Any]) -> bool:
    """
    Check if a Xero connection still exists in Xero.
    Returns True if connection exists in Xero, False if it was removed.
    Also updates xero_connection_id if missing.
    """
    if connection.get("software") != "xero":
        return True  # Not a Xero connection, skip
    
    connection_id = connection.get("id")
    access_token = connection.get("access_token")
    tenant_id = connection.get("tenant_id")
    
    if not access_token or not tenant_id:
        return False
    
    try:
        # Refresh token if expired to ensure we have a valid token
        if connection_manager.is_token_expired(connection_id):
            refresh_token = connection.get("refresh_token")
            if refresh_token:
                try:
                    import asyncio
                    token_response = await asyncio.to_thread(xero_client.refresh_token, refresh_token)
                    new_access_token = token_response.get("access_token")
                    new_refresh_token = token_response.get("refresh_token", refresh_token)
                    expires_in = token_response.get("expires_in", 1800)
                    
                    # Update connection with new tokens
                    connection_manager.update_connection(
                        connection_id,
                        access_token=new_access_token,
                        refresh_token=new_refresh_token,
                        expires_in=expires_in
                    )
                    
                    # Sync tokens to all connections sharing the same refresh_token
                    synced_count = connection_manager.sync_tokens_for_refresh_token(
                        refresh_token=refresh_token,
                        new_access_token=new_access_token,
                        new_refresh_token=new_refresh_token,
                        expires_in=expires_in,
                        software="xero"
                    )
                    logger.info(f"Token synchronization during connection check: {synced_count} Xero connection(s) updated")
                    
                    access_token = new_access_token
                except Exception as refresh_error:
                    # If refresh fails, connection might be invalid - check with existing token
                    logger.warning(f"Token refresh failed for connection {connection_id}: {str(refresh_error)}")
        
        # Get connections from Xero to check if this tenant still exists
        tenants = xero_client.get_connections(access_token)
        matching_tenant = next(
            (t for t in tenants if t.get("tenantId") == tenant_id),
            None
        )
        
        if matching_tenant:
            # Connection exists in Xero - update xero_connection_id if missing
            xero_connection_id = matching_tenant.get("id")
            # Check if we need to update xero_connection_id in tenant
            # This is called with temp_conn that has tenant_id set
            if not connection.get("xero_connection_id"):
                # Update the tenant's xero_connection_id in the connection's tenants array
                tenants = connection_manager.get_all_tenants_for_connection(connection_id)
                for tenant in tenants:
                    if tenant.get("tenant_id") == tenant_id:
                        tenant["xero_connection_id"] = xero_connection_id
                        connection_manager.update_connection(connection_id, tenants=tenants)
                        logger.info(f"Fetched and stored xero_connection_id={xero_connection_id} for tenant {tenant_id}")
                        break
            return True
        else:
            # Connection not found in Xero - it was removed
            logger.info(f"Connection {connection_id} (tenant_id={tenant_id}) not found in Xero - it was removed from Xero console")
            return False
    except Exception as e:
        # If API call fails, assume connection might be invalid/removed
        logger.warning(f"Could not verify Xero connection {connection_id}: {str(e)}")
        # Check if it's an authentication error (401/403) which likely means connection was removed
        error_str = str(e).lower()
        if "401" in error_str or "403" in error_str or "unauthorized" in error_str or "forbidden" in error_str:
            logger.info(f"Authentication error for connection {connection_id} - likely removed from Xero")
            return False
        # For other errors, assume connection still exists (don't delete on transient errors)
        return True


async def _ensure_xero_connection_id(connection: Dict[str, Any]) -> bool:
    """
    Ensure a Xero connection has xero_connection_id stored.
    Fetches it from Xero API if missing.
    Returns True if xero_connection_id is now available, False otherwise.
    """
    if connection.get("software") != "xero":
        return True  # Not a Xero connection, skip
    
    connection_id = connection.get("id")
    xero_connection_id = connection.get("xero_connection_id")
    
    # Already has xero_connection_id
    if xero_connection_id:
        return True
    
    # Use the check function which also updates xero_connection_id
    return await _check_xero_connection_exists(connection)


@app.get("/connections", response_class=HTMLResponse)
async def connections(request: Request):
    """Display connections page (renamed from settings)."""
    return await settings(request)


@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    """Display settings page with multiple connections."""
    # Migrate any active session-based Xero connection to connection manager
    # BUT only if we're not coming from a disconnect action
    disconnected = request.query_params.get("disconnected")
    
    if not disconnected:  # Only migrate if not disconnecting
        session_access_token = request.session.get("access_token")
        session_tenant_name = request.session.get("tenant_name")
        session_tenant_id = request.session.get("tenant_id")
        
        if session_access_token and session_tenant_id:
            # Check if this tenant already exists in any connection (check tenants array)
            all_existing = connection_manager.get_all_connections()
            tenant_exists = False
            
            for c in all_existing:
                if c.get("software") == "xero":
                    # Check old format (backward compatibility)
                    if c.get("tenant_id") == session_tenant_id:
                        tenant_exists = True
                        break
                    # Check new format (tenants array)
                    tenants = connection_manager.get_all_tenants_for_connection(c.get("id"))
                    if any(t.get("tenant_id") == session_tenant_id for t in tenants):
                        tenant_exists = True
                        break
            
            if not tenant_exists:
                # Migrate session connection to connection manager
                logger.info(f"Migrating session-based Xero connection: {session_tenant_name}")
                connection_manager.add_connection(
                    category="finance",
                    software="xero",
                    name=session_tenant_name or "Xero Connection",
                    access_token=session_access_token,
                    refresh_token=request.session.get("refresh_token"),
                    tenant_id=session_tenant_id,
                    tenant_name=session_tenant_name,
                    expires_in=request.session.get("expires_in", 1800),
                    metadata={"migrated_from_session": True}
                )
            else:
                # Tenant already exists - clear session to prevent re-migration
                logger.debug(f"Session tenant {session_tenant_id} already exists in connection manager, skipping migration")
                # Clear session data to prevent future migrations
                request.session.pop("access_token", None)
                request.session.pop("tenant_id", None)
                request.session.pop("tenant_name", None)
                request.session.pop("refresh_token", None)
    
    # Clean up duplicate connections (merge duplicates sharing same refresh_token)
    cleanup_count = connection_manager.cleanup_duplicate_connections()
    if cleanup_count > 0:
        logger.info(f"Cleaned up {cleanup_count} duplicate connection(s) on settings page load")
    
    # Load all connections
    all_connections = connection_manager.get_all_connections()
    
    # Check token expiry and filter connections
    # Show both active and expired connections (expired can be refreshed)
    # Only hide connections without access_token (disconnected)
    active_connections = []
    connections_to_delete = []
    
    for conn in all_connections:
        # Migrate old format to new format if needed
        if "tenants" not in conn:
            old_tenant_id = conn.get("tenant_id")
            if old_tenant_id:
                # Migrate to tenants array
                connection_manager.update_connection(
                    conn["id"],
                    tenants=[{
                        "tenant_id": old_tenant_id,
                        "tenant_name": conn.get("tenant_name"),
                        "xero_connection_id": conn.get("xero_connection_id")
                    }]
                )
                # Reload connection
                conn = connection_manager.get_connection(conn["id"])
        
        # Only include connections that have access_token
        if conn.get("access_token"):
            # For Xero connections, ensure tenants array is set
            # SKIP tenant verification on page load for performance - causes timeouts
            # Verification happens when user uses connection or clicks refresh
            if conn.get("software") == "xero":
                tenants = connection_manager.get_all_tenants_for_connection(conn["id"])
                # Just set tenants array - skip expensive API verification on page load
                conn["tenants"] = tenants if tenants else []
                # Verification disabled on page load - will happen when:
                # - User clicks "Refresh Token" button
                # - User tries to use connection (e.g., view accounts page)  
                # - User clicks "Remove Tenant" (verifies before removing)
                
                # Tenant verification DISABLED on page load for performance
                # Verification happens when:
                # - User clicks "Refresh Token" button  
                # - User tries to use connection (e.g., view accounts page)
                # - User clicks "Remove Tenant" (verifies before removing)
            
            # Check if token is expired
            is_expired = connection_manager.is_token_expired(conn["id"])
            conn["token_expired"] = is_expired
            # Include both active and expired connections (expired can be refreshed)
            active_connections.append(conn)
        else:
            # No access_token - disconnected, mark for deletion
            connections_to_delete.append(conn["id"])
    
    # Delete disconnected connections from storage (no access_token)
    for conn_id in connections_to_delete:
        logger.info(f"Deleting disconnected connection (no access_token): {conn_id}")
        connection_manager.delete_connection(conn_id)
    
    # Group Xero connections by refresh_token (one connection per OAuth authorization)
    # For other software types, keep as-is
    grouped_connections = {}
    xero_refresh_tokens_seen = set()
    
    for conn in active_connections:
        category = conn.get("category", "finance")
        software = conn.get("software")
        
        if software == "xero":
            refresh_token = conn.get("refresh_token")
            if refresh_token and refresh_token in xero_refresh_tokens_seen:
                # Skip - already have a connection for this refresh_token
                continue
            
            if refresh_token:
                xero_refresh_tokens_seen.add(refresh_token)
        
        if category not in grouped_connections:
            grouped_connections[category] = []
        grouped_connections[category].append(conn)
    
    # Use grouped_connections instead of connections_by_category
    connections_by_category = grouped_connections
    
    # Prepare software options for modal
    software_options = {}
    for category_key, category_info in connection_manager.SOFTWARE_CATEGORIES.items():
        software_options[category_key] = category_info["software"]
    
    # Check for success/error messages
    success = None
    error = None
    if request.query_params.get("disconnected") == "true":
        success = "Connection has been disconnected successfully."
    elif request.query_params.get("expired") == "true":
        error = "Connection has expired. Please reconnect."
    elif request.query_params.get("reconnected") == "true":
        success = "Connection has been reconnected successfully."
    elif request.query_params.get("added") == "true":
        success = "Connection added successfully."
    elif request.query_params.get("deleted") == "true":
        success = "Connection deleted successfully."
    elif request.query_params.get("tenant_removed") == "true":
        success = "Tenant has been removed successfully."
    
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "categories": connection_manager.SOFTWARE_CATEGORIES,
            "connections_by_category": connections_by_category,
            "software_info": {k: v for cat in connection_manager.SOFTWARE_CATEGORIES.values() for k, v in cat["software"].items()},
            "software_options": software_options,
            "success": success,
            "error": error
        }
    )


# Connection Management Routes

@app.post("/connections/add")
async def add_connection(request: Request):
    """Add a new connection."""
    form_data = await request.form()
    category = form_data.get("category")
    software = form_data.get("software")
    name = form_data.get("name")
    
    if not all([category, software, name]):
        return RedirectResponse(url="/settings?error=Missing required fields")
    
    # Create connection without tokens (will be added after OAuth)
    connection_id = connection_manager.add_connection(
        category=category,
        software=software,
        name=name,
        access_token="",  # Will be set after OAuth
        refresh_token=None,
        tenant_id=None,
        tenant_name=None
    )
    
    # Store connection ID in session for OAuth callback
    request.session["pending_connection_id"] = connection_id
    request.session["pending_software"] = software
    
    # Redirect to connect endpoint (use 303 to force GET method)
    return RedirectResponse(url=f"/connections/{connection_id}/connect", status_code=303)


@app.get("/connections/{connection_id}/connect")
async def connect_connection(request: Request, connection_id: str):
    """Start OAuth flow for a connection."""
    connection = connection_manager.get_connection(connection_id)
    if not connection:
        return RedirectResponse(url="/settings?error=Connection not found")
    
    software = connection.get("software")
    
    # Store connection ID in session for callback
    request.session["pending_connection_id"] = connection_id
    request.session["pending_software"] = software
    
    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    
    # Get authorization URL based on software
    try:
        if software == "xero":
            # Validate client_id before generating URL
            if not xero_client.client_id:
                logger.error("XERO_CLIENT_ID is not set when connecting connection")
                return RedirectResponse(url="/settings?error=Xero client ID is not configured. Please check your environment variables.")
            auth_url = xero_client.get_authorization_url(state=state)
        elif software == "quickbooks":
            # QuickBooks integration is under construction
            return RedirectResponse(url="/settings?error=QuickBooks integration is currently under construction. Please check back soon!")
        else:
            return RedirectResponse(url="/settings?error=Unsupported software type")
        
        logger.info(f"Redirecting to {software} authorization for connection {connection_id}")
        return RedirectResponse(url=auth_url, status_code=303)
    except Exception as e:
        logger.error(f"Error generating OAuth URL for {software}: {str(e)}", exc_info=True)
        return RedirectResponse(url=f"/settings?error=Failed to start OAuth flow: {str(e)}")


@app.post("/connections/{connection_id}/disconnect")
async def disconnect_connection(request: Request, connection_id: str):
    """Disconnect a connection by revoking access with Xero API, then deleting from storage."""
    connection = connection_manager.get_connection(connection_id)
    if not connection:
        return RedirectResponse(url="/settings?error=Connection not found")
    
    software = connection.get("software")
    access_token = connection.get("access_token")
    tenant_id = connection.get("tenant_id")
    
    # Check if this connection matches the session data (so we can clear session)
    session_tenant_id = request.session.get("tenant_id")
    matches_session = (session_tenant_id == tenant_id)
    
    # Disconnect from Xero backend if it's a Xero connection
    if software == "xero" and access_token:
        tenant_id = connection.get("tenant_id")
        tenant_name = connection.get("tenant_name")
        xero_connection_id = connection.get("xero_connection_id")
        
        logger.info(f"Disconnecting Xero connection: connection_id={connection_id}, tenant_id={tenant_id}, xero_connection_id={xero_connection_id}, tenant_name={tenant_name}")
        
        # If xero_connection_id is missing, try to fetch it from Xero API
        if not xero_connection_id:
            logger.info(f"xero_connection_id missing for connection {connection_id}, attempting to fetch from Xero API")
            try:
                # Refresh token first to ensure we have a valid token
                refresh_token = connection.get("refresh_token")
                if refresh_token:
                    try:
                        import asyncio
                        token_response = await asyncio.to_thread(xero_client.refresh_token, refresh_token)
                        access_token = token_response.get("access_token")
                    except:
                        pass  # Use existing token
                
                # Get connections to find the xero_connection_id for this tenant
                tenants = xero_client.get_connections(access_token)
                matching_tenant = next(
                    (t for t in tenants if t.get("tenantId") == tenant_id),
                    None
                )
                
                if matching_tenant:
                    xero_connection_id = matching_tenant.get("id")
                    # Update the connection with the xero_connection_id for future use
                    connection_manager.update_connection(connection_id, xero_connection_id=xero_connection_id)
                    logger.info(f"Found and stored xero_connection_id={xero_connection_id} for tenant {tenant_id}")
                else:
                    logger.error(f"Could not find tenant {tenant_id} in Xero connections")
                    return RedirectResponse(url="/settings?error=Could not find connection in Xero. The tenant may have been disconnected already.", status_code=303)
            except Exception as fetch_error:
                logger.error(f"Error fetching xero_connection_id: {str(fetch_error)}")
                return RedirectResponse(url=f"/settings?error=Could not fetch connection details from Xero: {str(fetch_error)}", status_code=303)
        
        if not xero_connection_id:
            logger.error(f"No xero_connection_id found for connection {connection_id}")
            return RedirectResponse(url="/settings?error=Connection ID not found. Cannot disconnect from Xero.", status_code=303)
        
        try:
            # Always try to refresh token before disconnect to ensure we have a valid token
            # Even if not expired, refreshing ensures we have the latest valid token
            refresh_token = connection.get("refresh_token")
            if refresh_token:
                try:
                    logger.info(f"Refreshing token before disconnect: {connection_id}")
                    import asyncio
                    token_response = await asyncio.to_thread(xero_client.refresh_token, refresh_token)
                    new_access_token = token_response.get("access_token")
                    if new_access_token:
                        access_token = new_access_token
                        logger.info(f"Token refreshed successfully for disconnect")
                    else:
                        logger.warning(f"Token refresh returned no access_token, using existing token")
                except Exception as refresh_error:
                    logger.warning(f"Could not refresh token for disconnect: {str(refresh_error)}, will try with existing token")
            else:
                logger.warning(f"No refresh token available for connection {connection_id}, using existing access_token")
            
            # Call Xero API to disconnect/revoke the connection using xero_connection_id
            logger.info(f"Calling Xero API to disconnect connection: xero_connection_id={xero_connection_id}")
            disconnected = xero_client.disconnect_connection(access_token, xero_connection_id)
            
            if disconnected:
                logger.info(f"Successfully disconnected Xero connection from backend: {connection_id} (xero_connection_id={xero_connection_id})")
            else:
                logger.error(f"Xero API disconnect returned False for {connection_id} (xero_connection_id={xero_connection_id}). Connection may still be active in Xero.")
                # Don't continue with local deletion if API call failed - user should know
                return RedirectResponse(url="/settings?error=Failed to disconnect from Xero. Please try refreshing the connection first, or disconnect manually from Xero.", status_code=303)
        except Exception as e:
            logger.error(f"Exception disconnecting from Xero API: {str(e)}", exc_info=True)
            return RedirectResponse(url=f"/settings?error=Error disconnecting from Xero: {str(e)}", status_code=303)
    
    # Delete ALL connections sharing the same refresh_token (to clean up duplicates)
    refresh_token = connection.get("refresh_token")
    if software == "xero" and refresh_token:
        duplicate_connections = connection_manager.get_connections_by_refresh_token(refresh_token, software="xero")
        deleted_count = 0
        for dup_conn in duplicate_connections:
            dup_conn_id = dup_conn.get("id")
            if dup_conn_id:
                connection_manager.delete_connection(dup_conn_id)
                deleted_count += 1
                logger.info(f"Deleted duplicate connection {dup_conn_id} (shared refresh_token)")
        logger.info(f"Deleted {deleted_count} connection(s) with refresh_token {refresh_token[:20]}...")
    else:
        # For non-Xero or connections without refresh_token, just delete this one
        connection_manager.delete_connection(connection_id)
        logger.info(f"Deleted connection {connection_id}")
    
    # Clear session if this connection matches the session data
    # Also clear if this is the only Xero connection (to prevent stale session data)
    if software == "xero":
        all_xero_connections = [c for c in connection_manager.get_all_connections() if c.get("software") == "xero" and c.get("access_token")]
        if matches_session or len(all_xero_connections) == 0:
            logger.info(f"Clearing session data for disconnected connection: {connection_id} (matches_session={matches_session}, remaining_xero={len(all_xero_connections)})")
            clear_xero_session(request)
    
    logger.info(f"Disconnected and deleted connection(s)")
    return RedirectResponse(url="/settings?disconnected=true", status_code=303)


@app.post("/connections/{connection_id}/refresh")
async def refresh_connection(request: Request, connection_id: str):
    """Refresh token for a connection."""
    connection = connection_manager.get_connection(connection_id)
    if not connection:
        return RedirectResponse(url="/settings?error=Connection not found")
    
    refresh_token = connection.get("refresh_token")
    if not refresh_token:
        return RedirectResponse(url="/settings?error=No refresh token available")
    
    software = connection.get("software")
    
    try:
        if software == "xero":
            import asyncio
            token_response = await asyncio.to_thread(xero_client.refresh_token, refresh_token)
        elif software == "quickbooks":
            # QuickBooks integration is under construction
            return RedirectResponse(url="/settings?error=QuickBooks integration is currently under construction. Please check back soon!")
        else:
            return RedirectResponse(url="/settings?error=Unsupported software type")
        
        # Update connection with new tokens
        new_access_token = token_response.get("access_token")
        new_refresh_token = token_response.get("refresh_token", refresh_token)  # Use new refresh_token if provided, otherwise keep old
        expires_in = token_response.get("expires_in", 1800)
        
        connection_manager.update_connection(
            connection_id,
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_in=expires_in
        )
        
        # For Xero connections, sync tokens to all connections sharing the same refresh_token
        # This ensures all tenants from the same OAuth authorization stay in sync
        if software == "xero":
            # Sync tokens to all connections with the same refresh_token
            synced_count = connection_manager.sync_tokens_for_refresh_token(
                refresh_token=refresh_token,
                new_access_token=new_access_token,
                new_refresh_token=new_refresh_token,
                expires_in=expires_in,
                software="xero"
            )
            logger.info(f"Token synchronization: {synced_count} Xero connection(s) updated with new tokens")
            
            # Ensure xero_connection_id is stored for the current connection
            existing_xero_connection_id = connection.get("xero_connection_id")
            if not existing_xero_connection_id and new_access_token:
                try:
                    tenant_id = connection.get("tenant_id")
                    if tenant_id:
                        # Fetch connections from Xero to get the connection ID
                        tenants = xero_client.get_connections(new_access_token)
                        matching_tenant = next(
                            (t for t in tenants if t.get("tenantId") == tenant_id),
                            None
                        )
                        if matching_tenant:
                            xero_connection_id = matching_tenant.get("id")
                            connection_manager.update_connection(
                                connection_id,
                                xero_connection_id=xero_connection_id
                            )
                            logger.info(f"Fetched and stored xero_connection_id={xero_connection_id} for connection {connection_id} during refresh")
                except Exception as fetch_error:
                    logger.warning(f"Could not fetch xero_connection_id during refresh: {str(fetch_error)}")
        
        logger.info(f"Refreshed token for connection: {connection_id}")
        return RedirectResponse(url="/settings?reconnected=true", status_code=303)
    except Exception as e:
        logger.error(f"Error refreshing token: {str(e)}")
        return RedirectResponse(url=f"/settings?error=Failed to refresh token: {str(e)}")


@app.post("/connections/{connection_id}/rename")
async def rename_connection(request: Request, connection_id: str):
    """Rename a connection."""
    form_data = await request.form()
    new_name = form_data.get("name", "").strip()
    
    if not new_name:
        return JSONResponse({"success": False, "error": "Name cannot be empty"})
    
    success = connection_manager.update_connection(connection_id, name=new_name)
    
    if success:
        return JSONResponse({"success": True})
    else:
        return JSONResponse({"success": False, "error": "Connection not found"})


@app.post("/connections/{connection_id}/delete")
async def delete_connection(request: Request, connection_id: str):
    """Delete a connection."""
    success = connection_manager.delete_connection(connection_id)
    
    if success:
        logger.info(f"Deleted connection: {connection_id}")
        return RedirectResponse(url="/settings?deleted=true")
    else:
        return RedirectResponse(url="/settings?error=Connection not found")


@app.post("/connections/{connection_id}/add-tenant")
async def add_tenant_to_connection(request: Request, connection_id: str):
    """Start OAuth flow to add tenants to an existing connection."""
    logger.info(f"=== ADD TENANT FLOW START ===")
    logger.info(f"Connection ID: {connection_id}")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request URL: {request.url}")
    
    connection = connection_manager.get_connection(connection_id)
    if not connection:
        logger.error(f"Connection {connection_id} not found")
        return RedirectResponse(url="/settings?error=Connection not found")
    
    software = connection.get("software")
    logger.info(f"Connection software: {software}")
    if software != "xero":
        return RedirectResponse(url="/settings?error=Add tenant only supported for Xero connections")
    
    # Validate Xero client configuration
    logger.info(f"=== XERO CLIENT CONFIGURATION CHECK ===")
    logger.info(f"Client ID exists: {bool(xero_client.client_id)}")
    logger.info(f"Client ID length: {len(xero_client.client_id) if xero_client.client_id else 0}")
    logger.info(f"Client ID preview: {xero_client.client_id[:15] + '...' if xero_client.client_id and len(xero_client.client_id) > 15 else (xero_client.client_id or 'NOT SET')}")
    logger.info(f"Redirect URI: {xero_client.redirect_uri}")
    logger.info(f"Redirect URI length: {len(xero_client.redirect_uri) if xero_client.redirect_uri else 0}")
    logger.info(f"Auth URL: {xero_client.auth_url}")
    logger.info(f"Scopes: {xero_client.scopes}")
    
    if not xero_client.client_id:
        logger.error("XERO_CLIENT_ID is not set in configuration")
        return RedirectResponse(url="/settings?error=Xero client ID is not configured. Please check your environment variables.")
    
    if not xero_client.redirect_uri:
        logger.error("XERO_REDIRECT_URI is not set in configuration")
        return RedirectResponse(url="/settings?error=Xero redirect URI is not configured. Please check your environment variables.")
    
    # Store connection ID in session for OAuth callback
    logger.info(f"=== SESSION SETUP ===")
    request.session["pending_connection_id"] = connection_id
    request.session["pending_software"] = software
    request.session["add_tenant_mode"] = True  # Flag to indicate we're adding tenants
    logger.info(f"Stored in session - pending_connection_id: {connection_id}")
    logger.info(f"Stored in session - pending_software: {software}")
    logger.info(f"Stored in session - add_tenant_mode: True")
    
    # Generate OAuth state
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    logger.info(f"Generated OAuth state: {state[:20]}... (length: {len(state)})")
    logger.info(f"Stored in session - oauth_state: {state[:20]}...")
    
    try:
        # Get authorization URL
        logger.info(f"=== GENERATING OAUTH URL ===")
        logger.info(f"Calling xero_client.get_authorization_url(state={state[:20]}...)")
        auth_url = xero_client.get_authorization_url(state=state)
        
        logger.info(f"=== OAUTH URL GENERATED SUCCESSFULLY ===")
        logger.info(f"Full OAuth URL length: {len(auth_url)}")
        logger.info(f"Full OAuth URL: {auth_url}")
        
        # Verify the URL is valid and can be parsed
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(auth_url)
            params = parse_qs(parsed.query)
            logger.info(f"=== URL VERIFICATION ===")
            logger.info(f"Scheme: {parsed.scheme}")
            logger.info(f"Netloc: {parsed.netloc}")
            logger.info(f"Path: {parsed.path}")
            logger.info(f"Client ID in URL: {params.get('client_id', [None])[0]}")
            logger.info(f"Redirect URI in URL: {params.get('redirect_uri', [None])[0]}")
            logger.info(f"State in URL: {params.get('state', [None])[0][:20] if params.get('state', [None])[0] else None}...")
        except Exception as e:
            logger.warning(f"Could not parse OAuth URL for verification: {str(e)}")
        
        logger.info(f"Redirecting browser to Xero authorization page")
        logger.info(f"=== ADD TENANT FLOW - REDIRECTING TO XERO ===")
        
        # Use 303 See Other instead of 307 to ensure GET method is used
        # This might help with browser/Xero session issues
        return RedirectResponse(url=auth_url, status_code=303)
    except ValueError as ve:
        logger.error(f"=== CONFIGURATION ERROR ===")
        logger.error(f"ValueError: {str(ve)}", exc_info=True)
        return RedirectResponse(url=f"/settings?error={str(ve)}")
    except Exception as e:
        logger.error(f"=== UNEXPECTED ERROR ===")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception message: {str(e)}", exc_info=True)
        return RedirectResponse(url=f"/settings?error=Failed to start OAuth flow: {str(e)}")


@app.post("/connections/{connection_id}/remove-tenant")
async def remove_tenant_from_connection(request: Request, connection_id: str):
    """Remove a tenant from a connection and disconnect it from Xero."""
    connection = connection_manager.get_connection(connection_id)
    if not connection:
        return RedirectResponse(url="/settings?error=Connection not found")
    
    form_data = await request.form()
    tenant_id = form_data.get("tenant_id")
    
    if not tenant_id:
        return RedirectResponse(url="/settings?error=Tenant ID required")
    
    # Find the tenant in the connection
    tenants = connection_manager.get_all_tenants_for_connection(connection_id)
    tenant_to_remove = next((t for t in tenants if t.get("tenant_id") == tenant_id), None)
    
    if not tenant_to_remove:
        return RedirectResponse(url="/settings?error=Tenant not found in connection")
    
    software = connection.get("software")
    access_token = connection.get("access_token")
    xero_connection_id = tenant_to_remove.get("xero_connection_id")
    
    # Disconnect from Xero backend if it's a Xero connection
    if software == "xero" and access_token and xero_connection_id:
        try:
            # Refresh token if expired to ensure we have a valid token
            if connection_manager.is_token_expired(connection_id):
                refresh_token = connection.get("refresh_token")
                if refresh_token:
                    try:
                        token_response = xero_client.refresh_token(refresh_token)
                        access_token = token_response.get("access_token")
                        # Sync tokens to all connections with same refresh_token
                        connection_manager.sync_tokens_for_refresh_token(
                            refresh_token=refresh_token,
                            new_access_token=token_response.get("access_token"),
                            new_refresh_token=token_response.get("refresh_token", refresh_token),
                            expires_in=token_response.get("expires_in", 1800),
                            software="xero"
                        )
                    except Exception:
                        pass  # Use existing token
            
            # Disconnect tenant from Xero
            disconnected = xero_client.disconnect_connection(access_token, xero_connection_id)
            if disconnected:
                logger.info(f"Disconnected tenant {tenant_id} from Xero backend")
            else:
                logger.warning(f"Failed to disconnect tenant {tenant_id} from Xero backend, but removing from connection anyway")
        except Exception as e:
            logger.error(f"Error disconnecting tenant from Xero: {str(e)}")
            return RedirectResponse(url=f"/settings?error=Failed to disconnect tenant from Xero: {str(e)}", status_code=303)
    
    # Remove tenant from ALL connections sharing the same refresh_token
    refresh_token = connection.get("refresh_token")
    if software == "xero" and refresh_token:
        # Find all connections with the same refresh_token
        duplicate_connections = connection_manager.get_connections_by_refresh_token(refresh_token, software="xero")
        success_count = 0
        for dup_conn in duplicate_connections:
            dup_conn_id = dup_conn.get("id")
            if dup_conn_id:
                # Remove tenant from each duplicate connection
                if connection_manager.remove_tenant(dup_conn_id, tenant_id):
                    success_count += 1
                    logger.info(f"Removed tenant {tenant_id} from connection {dup_conn_id}")
        
        if success_count > 0:
            # Check if any connection is now empty (they should all be in sync)
            remaining_tenants = connection_manager.get_all_tenants_for_connection(connection_id)
            if not remaining_tenants:
                # Delete ALL empty connections sharing the same refresh_token
                empty_connections = connection_manager.get_connections_by_refresh_token(refresh_token, software="xero")
                deleted_count = 0
                for empty_conn in empty_connections:
                    empty_conn_id = empty_conn.get("id")
                    if empty_conn_id:
                        connection_manager.delete_connection(empty_conn_id)
                        deleted_count += 1
                        logger.info(f"Deleted empty duplicate connection {empty_conn_id} (shared refresh_token)")
                logger.info(f"Deleted {deleted_count} empty connection(s) with refresh_token {refresh_token[:20]}...")
                return RedirectResponse(url="/settings?deleted=true", status_code=303)
            
            logger.info(f"Removed tenant {tenant_id} from {success_count} connection(s)")
            return RedirectResponse(url="/settings?tenant_removed=true", status_code=303)
        else:
            return RedirectResponse(url="/settings?error=Failed to remove tenant", status_code=303)
    else:
        # For non-Xero connections, use original logic
        success = connection_manager.remove_tenant(connection_id, tenant_id)
        
        if success:
            # Check if connection is now empty
            remaining_tenants = connection_manager.get_all_tenants_for_connection(connection_id)
            if not remaining_tenants:
                connection_manager.delete_connection(connection_id)
                logger.info(f"Deleted empty connection {connection_id} after removing last tenant")
                return RedirectResponse(url="/settings?deleted=true", status_code=303)
            
            logger.info(f"Removed tenant {tenant_id} from connection {connection_id}")
            return RedirectResponse(url="/settings?tenant_removed=true", status_code=303)
        else:
            return RedirectResponse(url="/settings?error=Failed to remove tenant", status_code=303)


@app.post("/connections/{connection_id}/disconnect-all")
async def disconnect_all_tenants(request: Request, connection_id: str):
    """Disconnect all tenants from a connection and delete it."""
    connection = connection_manager.get_connection(connection_id)
    if not connection:
        return RedirectResponse(url="/settings?error=Connection not found")
    
    tenants = connection_manager.get_all_tenants_for_connection(connection_id)
    software = connection.get("software")
    access_token = connection.get("access_token")
    refresh_token = connection.get("refresh_token")
    
    # Disconnect each tenant from Xero backend
    if software == "xero" and access_token:
        # Refresh token if expired
        if connection_manager.is_token_expired(connection_id):
            if refresh_token:
                try:
                    token_response = xero_client.refresh_token(refresh_token)
                    access_token = token_response.get("access_token")
                    connection_manager.sync_tokens_for_refresh_token(
                        refresh_token=refresh_token,
                        new_access_token=token_response.get("access_token"),
                        new_refresh_token=token_response.get("refresh_token", refresh_token),
                        expires_in=token_response.get("expires_in", 1800),
                        software="xero"
                    )
                except Exception:
                    pass
        
        for tenant in tenants:
            xero_connection_id = tenant.get("xero_connection_id")
            if xero_connection_id:
                try:
                    xero_client.disconnect_connection(access_token, xero_connection_id)
                    logger.info(f"Disconnected tenant {tenant.get('tenant_id')} from Xero")
                except Exception as e:
                    logger.warning(f"Failed to disconnect tenant {tenant.get('tenant_id')}: {str(e)}")
    
    # Delete ALL connections sharing the same refresh_token (to clean up duplicates)
    if software == "xero" and refresh_token:
        duplicate_connections = connection_manager.get_connections_by_refresh_token(refresh_token, software="xero")
        deleted_count = 0
        for dup_conn in duplicate_connections:
            dup_conn_id = dup_conn.get("id")
            if dup_conn_id:
                connection_manager.delete_connection(dup_conn_id)
                deleted_count += 1
                logger.info(f"Deleted duplicate connection {dup_conn_id} (shared refresh_token)")
        logger.info(f"Deleted {deleted_count} connection(s) with refresh_token {refresh_token[:20]}...")
    else:
        # For non-Xero or connections without refresh_token, just delete this one
        connection_manager.delete_connection(connection_id)
        logger.info(f"Deleted connection {connection_id}")
    
    return RedirectResponse(url="/settings?disconnected=true", status_code=303)


# OAuth Callback Routes
# Note: The /callback route is handled above (line 269) and redirects to /callback/{software}

@app.get("/callback/{software}")
async def callback_software(request: Request, software: str, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Handle OAuth callback for different software types."""
    logger.info(f"=== OAUTH CALLBACK RECEIVED (SOFTWARE ROUTE) ===")
    logger.info(f"Software: {software}")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request URL: {request.url}")
    logger.info(f"Full request URL: {str(request.url)}")
    logger.info(f"Query params: {dict(request.query_params)}")
    logger.info(f"Code parameter: {'present' if code else 'missing'} - {code[:30] + '...' if code and len(code) > 30 else code}")
    logger.info(f"State parameter: {state}")
    logger.info(f"Error parameter: {error}")
    logger.info(f"Error description: {request.query_params.get('error_description', 'Not provided')}")
    logger.info(f"Session keys: {list(request.session.keys())}")
    
    # Check for errors
    if error:
        logger.error(f"=== OAUTH ERROR FROM XERO (SOFTWARE ROUTE) ===")
        logger.error(f"OAuth error for {software}: {error}")
        logger.error(f"Error description: {request.query_params.get('error_description', 'Not provided')}")
        logger.error(f"Full error params: {dict(request.query_params)}")
        logger.error(f"Request URL: {request.url}")
        
        # If error is invalid_request or invalid_client_id, provide detailed debugging info
        if error in ["invalid_request", "invalid_client"]:
            logger.error(f"=== INVALID CLIENT_ID ERROR - DEBUGGING INFO ===")
            logger.error(f"Client ID being used: {xero_client.client_id}")
            logger.error(f"Client ID length: {len(xero_client.client_id) if xero_client.client_id else 0}")
            logger.error(f"Redirect URI being used: {xero_client.redirect_uri}")
            logger.error(f"Please check Xero Developer Portal (https://developer.xero.com/myapps):")
            logger.error(f"  1. Client ID must match exactly: {xero_client.client_id}")
            logger.error(f"  2. Redirect URI must match exactly: {xero_client.redirect_uri}")
            logger.error(f"  3. No trailing slashes, exact case, exact protocol (http vs https)")
        
        return RedirectResponse(url=f"/settings?error=Authentication failed: {error}. Check server logs for details.")
    
    # Verify state
    stored_state = request.session.get("oauth_state")
    logger.info(f"=== STATE VERIFICATION ===")
    logger.info(f"Stored state in session: {stored_state[:20] + '...' if stored_state and len(stored_state) > 20 else stored_state}")
    logger.info(f"Received state: {state}")
    logger.info(f"States match: {stored_state == state}")
    
    if not stored_state or stored_state != state:
        logger.error("=== STATE MISMATCH ===")
        logger.error(f"Stored state: {stored_state}")
        logger.error(f"Received state: {state}")
        return RedirectResponse(url="/settings?error=Invalid state parameter")
    
    if not code:
        logger.error("=== NO AUTHORIZATION CODE ===")
        logger.error("No authorization code received from Xero")
        return RedirectResponse(url="/settings?error=No authorization code received")
    
    # Get pending connection ID
    connection_id = request.session.get("pending_connection_id")
    add_tenant_mode = request.session.get("add_tenant_mode", False)
    logger.info(f"=== CALLBACK PROCESSING ===")
    logger.info(f"Connection ID from session: {connection_id}")
    logger.info(f"Add tenant mode: {add_tenant_mode}")
    logger.info(f"Authorization code received: {code[:30] + '...' if len(code) > 30 else code}")
    
    if not connection_id:
        return RedirectResponse(url="/settings?error=No pending connection found")
    
    try:
        logger.info(f"=== STARTING TOKEN EXCHANGE FOR {software.upper()} ===")
        logger.info(f"Authorization code length: {len(code) if code else 0}")
        logger.info(f"Pending connection ID: {connection_id}")
        
        # Exchange code for tokens based on software
        if software == "xero":
            import asyncio
            logger.info("=== STEP 1: TOKEN EXCHANGE ===")
            logger.info(f"Calling xero_client.get_access_token() with code length: {len(code) if code else 0}")
            logger.info(f"Code preview: {code[:20] + '...' if code and len(code) > 20 else code}")
            logger.info(f"Redirect URI: {xero_client.redirect_uri}")
            logger.info(f"Token URL: {xero_client.token_url}")
            
            try:
                token_response = await asyncio.to_thread(xero_client.get_access_token, code)
                logger.info("=== TOKEN EXCHANGE COMPLETED ===")
                logger.info(f"Token response keys: {list(token_response.keys()) if token_response else 'None'}")
                logger.info(f"Token response preview: {str(token_response)[:200] if token_response else 'None'}...")
            except Exception as token_error:
                logger.error(f"=== TOKEN EXCHANGE FAILED ===")
                logger.error(f"Error type: {type(token_error).__name__}")
                logger.error(f"Error message: {str(token_error)}", exc_info=True)
                raise
            
            access_token = token_response.get("access_token")
            refresh_token = token_response.get("refresh_token")
            expires_in = token_response.get("expires_in", 1800)
            
            logger.info(f"=== TOKEN EXTRACTION ===")
            logger.info(f"Access token present: {bool(access_token)}")
            logger.info(f"Access token length: {len(access_token) if access_token else 0}")
            logger.info(f"Access token preview: {access_token[:30] + '...' if access_token and len(access_token) > 30 else access_token}")
            logger.info(f"Refresh token present: {bool(refresh_token)}")
            logger.info(f"Refresh token length: {len(refresh_token) if refresh_token else 0}")
            logger.info(f"Expires in: {expires_in} seconds")
            
            if not access_token:
                logger.error("=== ERROR: NO ACCESS TOKEN IN RESPONSE ===")
                logger.error(f"Full token response: {token_response}")
                raise ValueError("No access token in response")
            
            # Get connected organizations (tenants)
            logger.info("=== STEP 2: GETTING CONNECTIONS ===")
            logger.info(f"Calling xero_client.get_connections() with access_token length: {len(access_token) if access_token else 0}")
            try:
                tenants = await asyncio.to_thread(xero_client.get_connections, access_token)
                logger.info("=== GET CONNECTIONS COMPLETED ===")
            except Exception as connections_error:
                logger.error(f"=== GET CONNECTIONS FAILED ===")
                logger.error(f"Error type: {type(connections_error).__name__}")
                logger.error(f"Error message: {str(connections_error)}", exc_info=True)
                raise
            
            logger.info(f"=== XERO CONNECTIONS API RESPONSE ===")
            logger.info(f"Tenants type: {type(tenants)}")
            logger.info(f"Number of tenants returned by Xero: {len(tenants) if tenants else 0}")
            logger.info(f"Tenants response (full): {tenants}")
            
            if not tenants:
                logger.error("=== ERROR: NO TENANTS RETURNED ===")
                logger.error(f"Tenants value: {tenants}")
                raise ValueError("No Xero organizations connected")
            
            # Build tenants list from OAuth response
            logger.info("=== STEP 3: BUILDING TENANTS LIST ===")
            tenants_list = []
            for idx, tenant in enumerate(tenants):
                logger.info(f"Processing tenant {idx + 1}/{len(tenants)}")
                logger.info(f"  Raw tenant data: {tenant}")
                logger.info(f"  Tenant keys: {list(tenant.keys()) if isinstance(tenant, dict) else 'Not a dict'}")
                
                tenant_id = tenant.get("tenantId")
                tenant_name = tenant.get("tenantName")
                xero_connection_id = tenant.get("id")  # This is the connection ID needed for DELETE
                
                logger.info(f"  Extracted tenant_id: {tenant_id}")
                logger.info(f"  Extracted tenant_name: {tenant_name}")
                logger.info(f"  Extracted xero_connection_id: {xero_connection_id}")
                
                if not tenant_id:
                    logger.warning(f"  Skipping tenant {idx + 1} - missing tenantId")
                    continue
                
                tenant_entry = {
                    "tenant_id": tenant_id,
                    "tenant_name": tenant_name,
                    "xero_connection_id": xero_connection_id
                }
                tenants_list.append(tenant_entry)
                logger.info(f"  Added tenant to list: {tenant_name} (ID: {tenant_id[:8]}...)")
            
            logger.info(f"=== TENANTS LIST BUILT ===")
            logger.info(f"Total tenants to process: {len(tenants_list)}")
            for idx, t in enumerate(tenants_list):
                logger.info(f"  {idx + 1}. {t.get('tenant_name')} (ID: {t.get('tenant_id', 'N/A')[:8]}..., Connection ID: {t.get('xero_connection_id', 'N/A')})")
            
            if add_tenant_mode:
                # Adding tenants to existing connection
                existing_connection = connection_manager.get_connection(connection_id)
                if not existing_connection:
                    return RedirectResponse(url="/settings?error=Connection not found")
                
                existing_tenants = connection_manager.get_all_tenants_for_connection(connection_id)
                existing_tenant_ids = {t.get("tenant_id") for t in existing_tenants}
                
                logger.info(f"=== ADDING TENANTS TO EXISTING CONNECTION ===")
                logger.info(f"Connection ID: {connection_id}")
                logger.info(f"Existing tenants: {len(existing_tenants)}")
                logger.info(f"Tenants to add: {len(tenants_list)}")
                
                added_count = 0
                skipped_count = 0
                for idx, tenant_data in enumerate(tenants_list):
                    tenant_id = tenant_data.get("tenant_id")
                    tenant_name = tenant_data.get("tenant_name")
                    
                    logger.info(f"Processing tenant {idx + 1}/{len(tenants_list)}: {tenant_name} (ID: {tenant_id[:8] if tenant_id else 'N/A'}...)")
                    
                    if tenant_id in existing_tenant_ids:
                        logger.info(f"  Tenant {tenant_name} already exists, skipping")
                        skipped_count += 1
                        continue
                    
                    logger.info(f"  Adding tenant {tenant_name} to connection {connection_id}")
                    try:
                        connection_manager.add_tenant(
                            connection_id,
                            tenant_id,
                            tenant_name,
                            tenant_data.get("xero_connection_id")
                        )
                        added_count += 1
                        logger.info(f"  Successfully added tenant {tenant_name}")
                    except Exception as e:
                        logger.error(f"  Failed to add tenant {tenant_name}: {str(e)}", exc_info=True)
                
                logger.info(f"=== TENANT ADDITION SUMMARY ===")
                logger.info(f"Added: {added_count}, Skipped (already exist): {skipped_count}, Total processed: {len(tenants_list)}")
                
                # Update tokens for the connection
                connection_manager.update_connection(
                    connection_id,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_in=expires_in
                )
                
                logger.info(f"Added {added_count} tenant(s) to connection {connection_id}")
                
                # Clear OAuth state and pending connection
                request.session.pop("oauth_state", None)
                request.session.pop("pending_connection_id", None)
                request.session.pop("pending_software", None)
                request.session.pop("add_tenant_mode", None)
                
                logger.info(f"Successfully added tenant(s) to connection {connection_id}")
                return RedirectResponse(url="/settings?reconnected=true", status_code=303)
            else:
                # Creating new connection
                logger.info("=== STEP 4: CREATING NEW CONNECTION ===")
                logger.info(f"Pending connection ID: {connection_id}")
                pending_connection = connection_manager.get_connection(connection_id)
                logger.info(f"Pending connection found: {pending_connection is not None}")
                if pending_connection:
                    logger.info(f"Pending connection data: {pending_connection}")
                
                connection_name = pending_connection.get("name", "Xero Connection") if pending_connection else "Xero Connection"
                category = pending_connection.get("category", "finance") if pending_connection else "finance"
                logger.info(f"Connection name: {connection_name}")
                logger.info(f"Category: {category}")
                
                # Check if a connection with the same refresh_token already exists
                logger.info(f"=== CHECKING FOR EXISTING CONNECTION ===")
                logger.info(f"Refresh token to check: {refresh_token[:20] + '...' if refresh_token and len(refresh_token) > 20 else refresh_token}")
                existing_connection = connection_manager.get_connection_by_refresh_token(refresh_token, software="xero")
                logger.info(f"Existing connection found: {existing_connection is not None}")
                if existing_connection:
                    logger.info(f"Existing connection ID: {existing_connection.get('id')}")
                    logger.info(f"Existing connection data: {existing_connection}")
                
                if existing_connection:
                    # Add tenants to existing connection (skip duplicates)
                    logger.info("=== MERGING INTO EXISTING CONNECTION ===")
                    existing_connection_id = existing_connection.get("id")
                    logger.info(f"Existing connection ID: {existing_connection_id}")
                    
                    existing_tenants = connection_manager.get_all_tenants_for_connection(existing_connection_id)
                    existing_tenant_ids = {t.get("tenant_id") for t in existing_tenants}
                    logger.info(f"Existing tenants count: {len(existing_tenants)}")
                    logger.info(f"Existing tenant IDs: {list(existing_tenant_ids)}")
                    
                    added_count = 0
                    for idx, tenant_data in enumerate(tenants_list):
                        tenant_id = tenant_data.get("tenant_id")
                        tenant_name = tenant_data.get("tenant_name")
                        logger.info(f"Processing tenant {idx + 1}/{len(tenants_list)}: {tenant_name} (ID: {tenant_id[:8] if tenant_id else 'N/A'}...)")
                        
                        if tenant_id not in existing_tenant_ids:
                            logger.info(f"  Adding tenant {tenant_name} to existing connection")
                            try:
                                connection_manager.add_tenant(
                                    existing_connection_id,
                                    tenant_id,
                                    tenant_data.get("tenant_name"),
                                    tenant_data.get("xero_connection_id")
                                )
                                added_count += 1
                                logger.info(f"  Successfully added tenant {tenant_name}")
                            except Exception as add_error:
                                logger.error(f"  Failed to add tenant {tenant_name}: {str(add_error)}", exc_info=True)
                        else:
                            logger.info(f"  Tenant {tenant_name} already exists, skipping")
                    
                    # Update tokens for the existing connection
                    logger.info(f"=== UPDATING TOKENS FOR EXISTING CONNECTION ===")
                    logger.info(f"Connection ID: {existing_connection_id}")
                    logger.info(f"Access token length: {len(access_token) if access_token else 0}")
                    logger.info(f"Refresh token length: {len(refresh_token) if refresh_token else 0}")
                    logger.info(f"Expires in: {expires_in}")
                    
                    try:
                        connection_manager.update_connection(
                            existing_connection_id,
                            access_token=access_token,
                            refresh_token=refresh_token,
                            expires_in=expires_in
                        )
                        logger.info("Successfully updated connection tokens")
                    except Exception as update_error:
                        logger.error(f"Failed to update connection tokens: {str(update_error)}", exc_info=True)
                        raise
                    
                    logger.info(f"Added {added_count} tenant(s) to existing connection {existing_connection_id}")
                    
                    # Delete the pending placeholder connection
                    if pending_connection:
                        logger.info(f"=== DELETING PLACEHOLDER CONNECTION ===")
                        logger.info(f"Placeholder connection ID: {connection_id}")
                        try:
                            connection_manager.delete_connection(connection_id)
                            logger.info(f"Successfully deleted placeholder connection: {connection_id}")
                        except Exception as delete_error:
                            logger.warning(f"Could not delete placeholder connection: {str(delete_error)}")
                    
                    # Clear OAuth state and pending connection
                    logger.info("=== CLEARING SESSION DATA ===")
                    request.session.pop("oauth_state", None)
                    request.session.pop("pending_connection_id", None)
                    request.session.pop("pending_software", None)
                    request.session.pop("add_tenant_mode", None)
                    logger.info("Session data cleared")
                    
                    logger.info(f"=== SUCCESS: MERGED INTO EXISTING CONNECTION ===")
                    logger.info(f"Successfully authenticated {software} (merged into existing connection)")
                    return RedirectResponse(url="/settings?reconnected=true", status_code=303)
                else:
                    # Check if any of the tenants already exist in another connection
                    # This prevents duplicate connections for the same tenant from different OAuth flows
                    all_existing_connections = connection_manager.get_all_xero_connections()
                    tenant_to_connection_map = {}
                    for existing_conn in all_existing_connections:
                        existing_tenants = connection_manager.get_all_tenants_for_connection(existing_conn.get("id"))
                        for tenant in existing_tenants:
                            tenant_id = tenant.get("tenant_id")
                            if tenant_id:
                                tenant_to_connection_map[tenant_id] = existing_conn.get("id")
                    
                    # Check if any tenant from this OAuth flow already exists
                    matching_connection_id = None
                    for tenant_data in tenants_list:
                        tenant_id = tenant_data.get("tenant_id")
                        if tenant_id and tenant_id in tenant_to_connection_map:
                            matching_connection_id = tenant_to_connection_map[tenant_id]
                            logger.info(f"Found existing connection {matching_connection_id} for tenant {tenant_id}")
                            break
                    
                    if matching_connection_id:
                        # Merge into existing connection instead of creating duplicate
                        existing_tenants = connection_manager.get_all_tenants_for_connection(matching_connection_id)
                        existing_tenant_ids = {t.get("tenant_id") for t in existing_tenants}
                        
                        added_count = 0
                        for tenant_data in tenants_list:
                            tenant_id = tenant_data.get("tenant_id")
                            if tenant_id not in existing_tenant_ids:
                                connection_manager.add_tenant(
                                    matching_connection_id,
                                    tenant_id,
                                    tenant_data.get("tenant_name"),
                                    tenant_data.get("xero_connection_id")
                                )
                                added_count += 1
                        
                        # Update tokens - use the newer refresh_token from this OAuth flow
                        connection_manager.update_connection(
                            matching_connection_id,
                            access_token=access_token,
                            refresh_token=refresh_token,
                            expires_in=expires_in
                        )
                        
                        logger.info(f"Merged OAuth flow into existing connection {matching_connection_id} (added {added_count} tenant(s))")
                        
                        # Delete the pending placeholder connection
                        if pending_connection:
                            try:
                                connection_manager.delete_connection(connection_id)
                                logger.info(f"Deleted placeholder connection: {connection_id}")
                            except:
                                pass  # Ignore if already deleted
                        
                        # Clear OAuth state and pending connection
                        request.session.pop("oauth_state", None)
                        request.session.pop("pending_connection_id", None)
                        request.session.pop("pending_software", None)
                        request.session.pop("add_tenant_mode", None)
                        
                        logger.info(f"Successfully authenticated {software} (merged into existing connection)")
                        return RedirectResponse(url="/settings?reconnected=true", status_code=303)
                    else:
                        # Create new connection with all tenants (truly new tenant)
                        logger.info(f"=== CREATING NEW CONNECTION ===")
                        logger.info(f"Connection name: {connection_name}")
                        logger.info(f"Category: {category}")
                        logger.info(f"Software: xero")
                        logger.info(f"Access token length: {len(access_token) if access_token else 0}")
                        logger.info(f"Refresh token length: {len(refresh_token) if refresh_token else 0}")
                        logger.info(f"Expires in: {expires_in}")
                        logger.info(f"Tenants to add: {len(tenants_list)}")
                        for idx, t in enumerate(tenants_list):
                            logger.info(f"  {idx + 1}. {t.get('tenant_name')} (ID: {t.get('tenant_id', 'N/A')[:8]}..., Connection ID: {t.get('xero_connection_id', 'N/A')})")
                        
                        try:
                            logger.info("Calling connection_manager.add_connection()...")
                            new_connection_id = connection_manager.add_connection(
                                category=category,
                                software="xero",
                                name=connection_name,
                                access_token=access_token,
                                refresh_token=refresh_token,
                                expires_in=expires_in,
                                tenants=tenants_list
                            )
                            logger.info(f"=== CONNECTION CREATED SUCCESSFULLY ===")
                            logger.info(f"New connection ID: {new_connection_id}")
                            logger.info(f"Connection name: {connection_name}")
                            logger.info(f"Tenants added: {len(tenants_list)}")
                        except Exception as create_error:
                            logger.error(f"=== ERROR CREATING CONNECTION ===")
                            logger.error(f"Error type: {type(create_error).__name__}")
                            logger.error(f"Error message: {str(create_error)}", exc_info=True)
                            raise
                        
                        # Verify tenants were added
                        logger.info(f"=== VERIFYING CONNECTION ===")
                        try:
                            verify_tenants = connection_manager.get_all_tenants_for_connection(new_connection_id)
                            logger.info(f"Verification: Connection {new_connection_id} now has {len(verify_tenants)} tenant(s)")
                            for t in verify_tenants:
                                logger.info(f"  - {t.get('tenant_name')} (ID: {t.get('tenant_id', 'N/A')[:8]}...)")
                            
                            if len(verify_tenants) != len(tenants_list):
                                logger.warning(f"WARNING: Expected {len(tenants_list)} tenants but found {len(verify_tenants)}")
                        except Exception as verify_error:
                            logger.error(f"Error verifying connection: {str(verify_error)}", exc_info=True)
                
                # Delete the pending placeholder connection
                logger.info("=== CLEANING UP PLACEHOLDER CONNECTION ===")
                if pending_connection:
                    logger.info(f"Placeholder connection ID: {connection_id}")
                    try:
                        connection_manager.delete_connection(connection_id)
                        logger.info(f"Successfully deleted placeholder connection: {connection_id}")
                    except Exception as delete_error:
                        logger.warning(f"Could not delete placeholder connection: {str(delete_error)}")
                
                # Clear OAuth state and pending connection
                logger.info("=== CLEARING SESSION DATA ===")
                request.session.pop("oauth_state", None)
                request.session.pop("pending_connection_id", None)
                request.session.pop("pending_software", None)
                request.session.pop("add_tenant_mode", None)
                logger.info("Session data cleared")
                
                logger.info(f"=== SUCCESS: OAUTH FLOW COMPLETED ===")
                logger.info(f"Successfully authenticated {software}")
                return RedirectResponse(url="/settings?reconnected=true", status_code=303)
            
        elif software == "quickbooks":
            # QuickBooks integration is under construction
            # Clear OAuth state and pending connection
            request.session.pop("oauth_state", None)
            request.session.pop("pending_connection_id", None)
            request.session.pop("pending_software", None)
            
            logger.info(f"QuickBooks connection attempted but not yet implemented: {connection_id}")
            return RedirectResponse(url="/settings?error=QuickBooks integration is currently under construction. Please check back soon!", status_code=303)
        
        else:
            # Clear OAuth state and pending connection
            request.session.pop("oauth_state", None)
            request.session.pop("pending_connection_id", None)
            request.session.pop("pending_software", None)
            return RedirectResponse(url="/settings?error=Unsupported software type", status_code=303)
    
    except Exception as e:
        logger.error(f"=== ERROR DURING OAUTH CALLBACK PROCESSING ===")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        logger.error(f"Software: {software}")
        logger.error(f"Connection ID from session: {request.session.get('pending_connection_id', 'NOT SET')}")
        logger.error(f"Add tenant mode: {request.session.get('add_tenant_mode', False)}")
        logger.error(f"OAuth state in session: {bool(request.session.get('oauth_state'))}")
        logger.error(f"Full traceback:", exc_info=True)
        logger.error(f"Add tenant mode: {request.session.get('add_tenant_mode', False)}")
        
        # Clear OAuth state on error
        request.session.pop("oauth_state", None)
        request.session.pop("pending_connection_id", None)
        request.session.pop("pending_software", None)
        request.session.pop("add_tenant_mode", None)
        
        return RedirectResponse(url=f"/settings?error=Authentication failed: {str(e)}", status_code=303)


# Legacy routes for backward compatibility

@app.post("/disconnect-xero")
async def disconnect_xero(request: Request):
    """Disconnect Xero integration (legacy route)."""
    # Find all Xero connections and delete them completely
    connections = connection_manager.get_all_connections()
    for conn in connections:
        if conn.get("software") == "xero" and conn.get("access_token"):
            # Delete the connection completely (removes from storage)
            connection_manager.delete_connection(conn["id"])
    
    # Also clear session
    clear_xero_session(request)
    
    logger.info("Xero connections disconnected and deleted")
    return RedirectResponse(url="/settings?disconnected=true", status_code=303)


@app.get("/reconnect-xero")
async def reconnect_xero(request: Request):
    """Reconnect Xero (legacy route)."""
    # Find first Xero connection or create one
    connections = connection_manager.get_all_connections()
    xero_conn = next((c for c in connections if c.get("software") == "xero"), None)
    
    if not xero_conn:
        # Create a default Xero connection
        connection_id = connection_manager.add_connection(
            category="finance",
            software="xero",
            name="Xero Connection",
            access_token=""
        )
    else:
        connection_id = xero_conn["id"]
    
    return RedirectResponse(url=f"/connections/{connection_id}/connect")


@app.get("/payroll-risk", response_class=HTMLResponse)
async def payroll_risk(request: Request):
    """Payroll Risk Early Warning - List view showing all analyses."""
    try:
        # Get all analyses from database
        analyses = payroll_risk_db.get_all_analyses()
        
        # Get all Xero connections (not just active ones) for the new analysis modal
        # We'll refresh tokens when starting the analysis if needed
        all_connections = connection_manager.get_all_connections()
        xero_connections = [conn for conn in all_connections if conn.get("software") == "xero"]
        
        # Ensure tenants are loaded for each connection
        for conn in xero_connections:
            if not conn.get("tenants"):
                tenants = connection_manager.get_all_tenants_for_connection(conn["id"])
                conn["tenants"] = tenants if tenants else []
        
        logger.info(f"Payroll risk page - Total Xero connections: {len(xero_connections)}")
        if xero_connections:
            logger.info(f"Xero connection names: {[c.get('name') for c in xero_connections]}")
        
        # Get categories for template compatibility
        selector_data = get_connections_for_selector()
        
        return templates.TemplateResponse(
            "payroll-risk.html",
            {
                "request": request,
                "view_mode": "list",
                "analyses": analyses,
                "connections": xero_connections,
                "categories": selector_data["categories"],
                "error": None
            }
        )
    
    except Exception as e:
        logger.error(f"Error in payroll-risk route: {str(e)}", exc_info=True)
        selector_data = get_connections_for_selector()
        return templates.TemplateResponse(
            "payroll-risk.html",
            {
                "request": request,
                "view_mode": "list",
                "analyses": [],
                "connections": selector_data["connections"],
                "categories": selector_data["categories"],
                "error": f"Failed to load payroll risk page: {str(e)}"
            }
        )


@app.get("/payroll-risk/{analysis_id}", response_class=HTMLResponse)
async def payroll_risk_details(request: Request, analysis_id: str):
    """Payroll Risk Analysis Details page."""
    try:
        # Get analysis from database
        analysis = payroll_risk_db.get_analysis(analysis_id)
        
        if not analysis:
            return RedirectResponse(url="/payroll-risk?error=Analysis not found", status_code=303)
        
        # Get all Xero connections for template compatibility
        all_connections = connection_manager.get_all_connections()
        xero_connections = [conn for conn in all_connections if conn.get("software") == "xero"]
        
        # Ensure tenants are loaded
        for conn in xero_connections:
            if not conn.get("tenants"):
                tenants = connection_manager.get_all_tenants_for_connection(conn["id"])
                conn["tenants"] = tenants if tenants else []
        
        # Get categories for template compatibility
        selector_data = get_connections_for_selector()
        
        return templates.TemplateResponse(
            "payroll-risk.html",
            {
                "request": request,
                "view_mode": "details",
                "analysis": analysis,
                "connections": xero_connections,
                "categories": selector_data["categories"],
                "error": None
            }
        )
    
    except Exception as e:
        logger.error(f"Error loading payroll risk details: {str(e)}", exc_info=True)
        return RedirectResponse(url=f"/payroll-risk?error={str(e)}", status_code=303)


@app.post("/payroll-risk/new", response_class=RedirectResponse)
async def start_payroll_risk_analysis(request: Request):
    """Start a new payroll risk analysis."""
    try:
        form_data = await request.form()
        connection_id = form_data.get("connection_id")
        tenant_id = form_data.get("tenant_id")
        
        if not connection_id:
            return RedirectResponse(url="/payroll-risk?error=Please select a connection", status_code=303)
        
        # Get connection details
        connection = connection_manager.get_connection(connection_id)
        if not connection:
            return RedirectResponse(url="/payroll-risk?error=Connection not found", status_code=303)
        
        if connection.get("software") != "xero":
            return RedirectResponse(url="/payroll-risk?error=Payroll risk analysis is only available for Xero connections", status_code=303)
        
        # Get tenant details if provided
        tenant_name = None
        if tenant_id:
            tenants = connection_manager.get_all_tenants_for_connection(connection_id)
            tenant = next((t for t in tenants if t.get("tenant_id") == tenant_id), None)
            if tenant:
                tenant_name = tenant.get("tenant_name")
            else:
                return RedirectResponse(url="/payroll-risk?error=Tenant not found", status_code=303)
        
        # Get access token directly from connection
        access_token = connection.get("access_token")
        refresh_token = connection.get("refresh_token")
        
        # Refresh token if expired
        if refresh_token:
            try:
                # Check if token is expired
                token_created_at_str = connection.get("token_created_at")
                expires_in = connection.get("expires_in", 1800)
                
                if token_created_at_str:
                    token_created_at = datetime.fromisoformat(token_created_at_str)
                    expiration_time = token_created_at + timedelta(seconds=expires_in)
                    if datetime.now() >= (expiration_time - timedelta(seconds=60)):
                        # Token expired, refresh it
                        logger.info(f"Token expired, refreshing for analysis {analysis_id}")
                        token_response = await asyncio.to_thread(xero_client.refresh_token, refresh_token)
                        access_token = token_response.get("access_token")
                        new_refresh_token = token_response.get("refresh_token", refresh_token)
                        
                        # Update connection with new tokens
                        connection_manager.update_connection(
                            connection_id,
                            access_token=access_token,
                            refresh_token=new_refresh_token,
                            expires_in=token_response.get("expires_in", 1800)
                        )
            except Exception as refresh_error:
                logger.error(f"Error refreshing token: {str(refresh_error)}")
                return RedirectResponse(url="/payroll-risk?error=Failed to refresh token. Please reconnect.", status_code=303)
        
        if not access_token:
            return RedirectResponse(url="/payroll-risk?error=No access token available. Please reconnect.", status_code=303)
        
        # Create new analysis record
        analysis_id = str(uuid.uuid4())
        connection_name = connection.get("name", "Unknown Connection")
        
        payroll_risk_db.create_analysis(
            analysis_id=analysis_id,
            connection_id=connection_id,
            connection_name=connection_name,
            tenant_id=tenant_id,
            tenant_name=tenant_name
        )
        
        # Start background task
        llm_model = config.OPENAI_MODEL if config.LLM_PROVIDER == "openai" else None
        asyncio.create_task(_run_payroll_risk_async(
            analysis_id=analysis_id,
            connection_id=connection_id,
            connection_name=connection_name,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            access_token=access_token,
            llm_model=llm_model
        ))
        
        logger.info(f"Started new payroll risk analysis: {analysis_id}")
        return RedirectResponse(url=f"/payroll-risk/{analysis_id}", status_code=303)
    
    except Exception as e:
        logger.error(f"Error starting payroll risk analysis: {str(e)}", exc_info=True)
        return RedirectResponse(url=f"/payroll-risk?error={str(e)}", status_code=303)


@app.get("/payroll-risk/{analysis_id}/progress", response_class=JSONResponse)
async def payroll_risk_progress(request: Request, analysis_id: str):
    """Get progress for a specific analysis."""
    try:
        # Check in-memory progress first
        progress_key = f"payroll_risk_progress_{analysis_id}"
        if progress_key in _payroll_risk_progress:
            progress_data = _payroll_risk_progress[progress_key]
            return JSONResponse({
                "status": progress_data["status"],
                "progress": progress_data["progress"],
                "message": progress_data["message"],
                "error": progress_data.get("error")
            })
        
        # Fall back to database
        analysis = payroll_risk_db.get_analysis(analysis_id)
        if not analysis:
            return JSONResponse({"error": "Analysis not found"}, status_code=404)
        
        return JSONResponse({
            "status": analysis["status"],
            "progress": analysis.get("progress", 0),
            "message": analysis.get("progress_message", ""),
            "error": analysis.get("error_message")
        })
    
    except Exception as e:
        logger.error(f"Error getting progress: {str(e)}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/connections/{connection_id}/tenants", response_class=JSONResponse)
async def get_connection_tenants(request: Request, connection_id: str):
    """Get tenants for a connection."""
    try:
        connection = connection_manager.get_connection(connection_id)
        if not connection:
            return JSONResponse({"error": "Connection not found"}, status_code=404)
        
        tenants = connection_manager.get_all_tenants_for_connection(connection_id)
        return JSONResponse({"tenants": tenants})
    
    except Exception as e:
        logger.error(f"Error getting tenants: {str(e)}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/logout")
async def logout(request: Request):
    """Clear session and logout."""
    clear_xero_session(request)
    request.session.clear()
    return RedirectResponse(url="/settings")


@app.get("/pe", response_class=HTMLResponse)
async def create_payroll_entries(request: Request):
    """Create payroll journal entries for bi-weekly payroll."""
    # Check authentication and token expiration
    if not is_authenticated(request):
        return RedirectResponse(url="/settings?expired=true")
    
    # Check and refresh token if needed
    if not check_and_refresh_token(request):
        return RedirectResponse(url="/settings?expired=true")
    
    access_token = request.session.get("access_token")
    tenant_name = request.session.get("tenant_name", "Unknown")
    
    mcp_client = None
    created_journals = []
    errors = []
    
    try:
        # Initialize MCP client
        logger.info("Initializing MCP client for payroll entries...")
        mcp_client = XeroMCPClient(bearer_token=access_token)
        
        # Define employees (example data - you can modify these)
        # Total payroll per bi-weekly period: $500
        employees = [
            {"name": "John Smith", "gross": 200.00, "tax_rate": 0.20, "super_rate": 0.10},
            {"name": "Jane Doe", "gross": 150.00, "tax_rate": 0.20, "super_rate": 0.10},
            {"name": "Bob Johnson", "gross": 150.00, "tax_rate": 0.20, "super_rate": 0.10},
        ]
        
        # Calculate amounts for each employee
        for emp in employees:
            emp["tax"] = round(emp["gross"] * emp["tax_rate"], 2)
            emp["super"] = round(emp["gross"] * emp["super_rate"], 2)
            emp["net"] = round(emp["gross"] - emp["tax"] - emp["super"], 2)
        
        # Calculate totals
        total_gross = sum(emp["gross"] for emp in employees)
        total_tax = sum(emp["tax"] for emp in employees)
        total_super = sum(emp["super"] for emp in employees)
        total_net = sum(emp["net"] for emp in employees)
        
        # Verify the math balances
        balance_check = total_gross - total_tax - total_super - total_net
        if abs(balance_check) > 0.01:  # Allow for rounding
            errors.append(f"Journal entry does not balance! Difference: ${balance_check:.2f}")
            logger.error(f"Payroll entry imbalance: {balance_check}")
        
        # First, delete/void the incorrectly created journals from Jan-Feb 2026
        journals_to_delete = [
            "b501baa8-8c28-4cee-b712-3c8db256ada7",  # Period 1 - 2026-01-01
            "260e66c8-e0f1-4f41-b912-2bf15a30dedd",  # Period 2 - 2026-01-16
            "f9f1d3c5-54d8-4884-88de-0373c82efb3f",  # Period 3 - 2026-01-31
            "477b21b5-f666-4830-a2c7-4232f1aa1598",  # Period 4 - 2026-02-15
        ]
        
        logger.info("Voiding incorrectly created journals from Jan-Feb 2026...")
        for journal_id in journals_to_delete:
            try:
                result = await mcp_client.call_tool(
                    "update-manual-journal",
                    {
                        "manualJournalID": journal_id,
                        "status": "VOID"
                    }
                )
                logger.info(f"Voided journal {journal_id}: {result}")
            except Exception as e:
                logger.warning(f"Could not void journal {journal_id}: {str(e)}")
                errors.append(f"Could not void journal {journal_id}: {str(e)}")
        
        # Create journal entries for the last 3 months (Oct, Nov, Dec 2025)
        # Bi-weekly payroll on 1st and 15th of each month = 6 entries total
        pay_dates = [
            datetime(2025, 10, 1).date(),   # October 1, 2025
            datetime(2025, 10, 15).date(),  # October 15, 2025
            datetime(2025, 11, 1).date(),   # November 1, 2025
            datetime(2025, 11, 15).date(),  # November 15, 2025
            datetime(2025, 12, 1).date(),   # December 1, 2025
            datetime(2025, 12, 15).date(),  # December 15, 2025
        ]
        
        for period, pay_date in enumerate(pay_dates, 1):
            
            # Create journal lines
            # Note: Xero restricts which accounts can be used in manual journals
            # Bank accounts, Accounts Payable, and some liability accounts are not allowed
            # Using a 3-line entry: Wages expense, Tax payable, and Superannuation+Net Pay combined
            # The net pay portion will be tracked within Superannuation Payable account
            journal_lines = [
                {
                    "lineAmount": round(total_gross, 2),  # Debit (positive)
                    "accountCode": "477",  # Wages and Salaries
                    "description": f"Bi-weekly payroll - {pay_date.strftime('%Y-%m-%d')}"
                },
                {
                    "lineAmount": round(-total_tax, 2),  # Credit (negative)
                    "accountCode": "825",  # Employee Tax Payable
                    "description": f"Tax withheld for {len(employees)} employees"
                },
                {
                    "lineAmount": round(-(total_super + total_net), 2),  # Credit (negative) - combines super + net pay
                    "accountCode": "826",  # Superannuation Payable (includes net pay: ${total_net:.2f} + super: ${total_super:.2f})
                    "description": f"Superannuation (${total_super:.2f}) + Net pay owed (${total_net:.2f}) for {len(employees)} employees"
                }
            ]
            
            # Create the journal entry via MCP
            try:
                logger.info(f"Creating payroll journal for {pay_date.strftime('%Y-%m-%d')}...")
                result = await mcp_client.call_tool(
                    "create-manual-journal",
                    {
                        "narration": f"Bi-weekly Payroll - {pay_date.strftime('%B %d, %Y')}",
                        "manualJournalLines": journal_lines,
                        "date": pay_date.strftime("%Y-%m-%d"),
                        "status": "POSTED"
                    }
                )
                
                # Parse the result
                if isinstance(result, dict) and "content" in result:
                    content = result["content"]
                    if isinstance(content, list) and len(content) > 0:
                        result_text = content[0].get("text", "")
                        if "Error" in result_text:
                            errors.append(f"Period {period + 1} ({pay_date}): {result_text}")
                        else:
                            created_journals.append({
                                "period": period + 1,
                                "date": pay_date.strftime("%Y-%m-%d"),
                                "result": result_text
                            })
                            logger.info(f"Successfully created journal for {pay_date}")
                
            except Exception as e:
                error_msg = f"Period {period + 1} ({pay_date}): {str(e)}"
                errors.append(error_msg)
                logger.error(f"Error creating journal entry: {error_msg}", exc_info=True)
        
        # Close MCP client
        await mcp_client.close()
        mcp_client = None
        
        # Prepare summary
        summary = {
            "total_periods": len(pay_dates),
            "created": len(created_journals),
            "errors": len(errors),
            "employees": employees,
            "totals": {
                "gross": total_gross,
                "tax": total_tax,
                "super": total_super,
                "net": total_net
            }
        }
        
        return templates.TemplateResponse(
            "payroll-entries.html",
            {
                "request": request,
                "tenant_name": tenant_name,
                "summary": summary,
                "created_journals": created_journals,
                "errors": errors
            }
        )
    
    except Exception as e:
        logger.error(f"Error in payroll entries creation: {str(e)}", exc_info=True)
        
        # Ensure MCP client is closed
        if mcp_client:
            try:
                await mcp_client.close()
            except:
                pass
        
        return templates.TemplateResponse(
            "payroll-entries.html",
            {
                "request": request,
                "tenant_name": tenant_name,
                "error": f"Failed to create payroll entries: {str(e)}",
                "summary": None,
                "created_journals": [],
                "errors": [str(e)]
            }
        )


async def _extract_journal_lines_from_xero_api(
    access_token: str, 
    tenant_id: str, 
    manual_journal_id: str
) -> List[Dict[str, Any]]:
    """
    Fetch journal line items directly from Xero API to bypass MCP server bug.
    
    Args:
        access_token: Valid OAuth access token
        tenant_id: Xero tenant/organization ID
        manual_journal_id: The manual journal ID to fetch
        
    Returns:
        List of journal line items with accountCode, lineAmount, description, taxType
    """
    journal_lines = []
    
    try:
        from app.xero_client import XeroClient
        xero_client = XeroClient()
        
        # Fetch manual journal directly from Xero API
        result = xero_client.get_manual_journal(access_token, tenant_id, manual_journal_id)
        
        # Extract journal lines from Xero API response
        if isinstance(result, dict) and "ManualJournals" in result:
            manual_journals = result["ManualJournals"]
            if manual_journals and len(manual_journals) > 0:
                journal = manual_journals[0]
                if "JournalLines" in journal:
                    for line in journal["JournalLines"]:
                        line_data = {
                            "lineAmount": float(line.get("LineAmount", 0)),
                            "accountCode": line.get("AccountCode", ""),
                            "description": line.get("Description", ""),
                            "taxType": line.get("TaxType", "NONE")
                        }
                        journal_lines.append(line_data)
                        logger.debug(f"Extracted line: Account {line_data['accountCode']}, Amount {line_data['lineAmount']}")
        
        logger.info(f"Fetched {len(journal_lines)} journal lines from Xero API for journal {manual_journal_id[:8]}...")
        
    except Exception as e:
        logger.error(f"Error fetching journal from Xero API: {str(e)}", exc_info=True)
    
    return journal_lines


async def _extract_journal_lines_from_detail(detail_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract journal line items from detailed journal entry response (fallback method)."""
    journal_lines = []
    
    if not isinstance(detail_result, dict) or "content" not in detail_result:
        return journal_lines
    
    content = detail_result["content"]
    if not isinstance(content, list):
        return journal_lines
    
    # Extract text from all content items
    full_text = ""
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            full_text += item.get("text", "") + "\n"
    
    # Check if the detailed entry also has [object Object]
    if "[object Object]" in full_text:
        logger.debug("Detailed entry also contains [object Object] - cannot extract from MCP response")
        return journal_lines
    
    # Parse line items from the text
    lines = full_text.split("\n")
    current_line_data = {}
    
    for line in lines:
        # Look for Line Amount
        amount_match = re.search(r'Line Amount[:\s]+([-]?\d+\.?\d*)', line, re.IGNORECASE)
        if amount_match:
            try:
                current_line_data["lineAmount"] = float(amount_match.group(1))
            except ValueError:
                pass
        
        # Look for Account Code
        account_match = re.search(r'Account Code[:\s]+(\d+)', line, re.IGNORECASE)
        if account_match:
            current_line_data["accountCode"] = account_match.group(1)
        
        # Look for Description
        desc_match = re.search(r'Description[:\s]+([^\n]+)', line, re.IGNORECASE)
        if desc_match:
            current_line_data["description"] = desc_match.group(1).strip()
        
        # Look for Tax Type
        tax_match = re.search(r'Tax Type[:\s]+([^\n]+)', line, re.IGNORECASE)
        if tax_match:
            current_line_data["taxType"] = tax_match.group(1).strip()
        
        # If we have both amount and account code, we have a complete line item
        if "lineAmount" in current_line_data and "accountCode" in current_line_data:
            journal_lines.append(current_line_data.copy())
            current_line_data = {}  # Reset for next line item
    
    return journal_lines


def _format_journal_line_items(journal_lines: List[Dict[str, Any]]) -> str:
    """Format journal line items as readable text."""
    if not journal_lines:
        return "No journal lines available"
    
    formatted_lines = []
    for i, line in enumerate(journal_lines, 1):
        parts = [f"Line {i}:"]
        
        if "description" in line:
            parts.append(f"Description: {line['description']}")
        if "accountCode" in line:
            parts.append(f"Account Code: {line['accountCode']}")
        if "lineAmount" in line:
            amount = line["lineAmount"]
            parts.append(f"Line Amount: ${abs(amount):.2f}" + (" (credit)" if amount < 0 else " (debit)"))
        if "taxType" in line:
            parts.append(f"Tax Type: {line['taxType']}")
        
        formatted_lines.append(" | ".join(parts))
    
    return "\n".join(formatted_lines)


async def _process_manual_journals_content(
    content: List[Dict[str, Any]], 
    mcp_client: XeroMCPClient,
    access_token: Optional[str] = None,
    tenant_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Process manual journals content array and fix [object Object] entries."""
    processed_content = []
    
    for idx, item in enumerate(content):
        if not isinstance(item, dict) or item.get("type") != "text":
            processed_content.append(item)
            continue
        
        text = item.get("text", "")
        
        # Check if this journal entry has [object Object]
        if "[object Object]" in text:
            # Extract journal ID
            journal_id_match = re.search(r'Manual Journal ID[:\s]+([a-f0-9-]{36})', text, re.IGNORECASE)
            
            if journal_id_match:
                journal_id = journal_id_match.group(1)
                logger.info(f"Found [object Object] in journal {journal_id[:8]}..., fetching detailed entry...")
                
                try:
                    journal_lines = []
                    
                    # First, try to fetch directly from Xero API (bypasses MCP server bug)
                    if access_token and tenant_id:
                        try:
                            # Fetch directly from Xero API
                            journal_lines = await _extract_journal_lines_from_xero_api(
                                access_token, tenant_id, journal_id
                            )
                        except Exception as api_error:
                            logger.warning(f"Failed to fetch from Xero API: {api_error}, trying MCP server as fallback...")
                    
                    # If Xero API failed, try MCP server (though it likely has the same bug)
                    if not journal_lines:
                        detail_result = await mcp_client.call_tool("list-manual-journals", {"manualJournalId": journal_id})
                        if detail_result:
                            journal_lines = await _extract_journal_lines_from_detail(detail_result)
                    
                    if journal_lines:
                        # Format the line items
                        formatted_lines = _format_journal_line_items(journal_lines)
                        
                        # Replace [object Object] with formatted line items
                        text = text.replace("[object Object],[object Object],[object Object]", formatted_lines)
                        text = text.replace("[object Object]", formatted_lines)
                        
                        logger.info(f"✓ Fixed journal {journal_id[:8]}... with {len(journal_lines)} line items")
                    else:
                        # Couldn't extract lines, add a note
                        text = text.replace("[object Object],[object Object],[object Object]", "[Journal line details could not be extracted]")
                        text = text.replace("[object Object]", "[Journal line details could not be extracted]")
                        logger.warning(f"Could not extract line items for journal {journal_id[:8]}...")
                
                except Exception as e:
                    logger.error(f"Error processing journal {journal_id_match.group(1)[:8] if journal_id_match else 'unknown'}...: {str(e)}")
                    # Replace with error note
                    text = text.replace("[object Object],[object Object],[object Object]", f"[Error fetching details: {str(e)}]")
                    text = text.replace("[object Object]", f"[Error fetching details: {str(e)}]")
            
            else:
                # Couldn't extract journal ID, just replace the text
                text = text.replace("[object Object],[object Object],[object Object]", "[Journal line details unavailable - journal ID not found]")
                text = text.replace("[object Object]", "[Journal line details unavailable - journal ID not found]")
                logger.warning("Could not extract journal ID from text with [object Object]")
        
        # Create new item with processed text
        processed_item = item.copy()
        processed_item["text"] = text
        processed_content.append(processed_item)
    
    return processed_content


def _format_date(date_str: str) -> str:
    """Format date string to dd-mm-yyyy format."""
    if not date_str or date_str == 'N/A':
        return 'N/A'
    
    try:
        # Try parsing common date formats
        from datetime import datetime
        
        # Try ISO format first (yyyy-mm-dd)
        if '-' in date_str:
            parts = date_str.split('-')
            if len(parts) == 3:
                # Check if it's ISO format (yyyy-mm-dd)
                if len(parts[0]) == 4:
                    dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
                    return dt.strftime('%d-%m-%Y')
                # Or already dd-mm-yyyy
                elif len(parts[2]) == 4:
                    return date_str[:10]
        
        # Try other formats
        for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%m/%d/%Y']:
            try:
                dt = datetime.strptime(date_str[:10], fmt)
                return dt.strftime('%d-%m-%Y')
            except:
                continue
        
        # If all parsing fails, return original
        return date_str[:10] if len(date_str) >= 10 else date_str
    except Exception:
        return date_str


def _parse_manual_journal_text(text: str) -> Dict[str, Any]:
    """Parse manual journal text into structured data."""
    journal = {
        "id": "",
        "narration": "",
        "date": "",
        "status": "",
        "journal_number": "",
        "total": 0.0,
        "lines": [],
        "raw_text": text
    }
    
    lines = text.split("\n")
    current_line = {}
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if "Manual Journal ID:" in line:
            journal["id"] = line.split(":", 1)[1].strip()
        elif "Narration:" in line or "Description:" in line:
            journal["narration"] = line.split(":", 1)[1].strip()
        elif "Date:" in line:
            date_str = line.split(":", 1)[1].strip()
            journal["date"] = _format_date(date_str)
        elif "Status:" in line:
            journal["status"] = line.split(":", 1)[1].strip()
        elif "Journal Number:" in line:
            journal["journal_number"] = line.split(":", 1)[1].strip()
        elif "Line Amount:" in line:
            try:
                amount_str = line.split(":", 1)[1].strip()
                # Remove currency symbols and parse
                amount = float(re.sub(r'[^\d.-]', '', amount_str))
                current_line["lineAmount"] = amount
            except (ValueError, IndexError):
                pass
        elif "Account Code:" in line:
            current_line["accountCode"] = line.split(":", 1)[1].strip()
        elif "Description:" in line and "Line" not in line:
            # This might be line description
            if "accountCode" in current_line:
                current_line["description"] = line.split(":", 1)[1].strip()
        elif "Tax Type:" in line:
            current_line["taxType"] = line.split(":", 1)[1].strip()
            # Complete line item
            if "lineAmount" in current_line and "accountCode" in current_line:
                journal["lines"].append(current_line.copy())
                journal["total"] += abs(current_line.get("lineAmount", 0))
                current_line = {}
    
    return journal


def _parse_bank_transaction_text(text: str) -> Dict[str, Any]:
    """Parse bank transaction text into structured data."""
    transaction = {
        "id": "",
        "date": "",
        "contact": "",
        "line_items": [],
        "total": 0.0,
        "type": "",
        "status": "",
        "reference": "",
        "raw_text": text
    }
    
    lines = text.split("\n")
    current_item = {}
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if "Bank Transaction ID:" in line or "Transaction ID:" in line:
            transaction["id"] = line.split(":", 1)[1].strip()
        elif "Date:" in line:
            date_str = line.split(":", 1)[1].strip()
            transaction["date"] = _format_date(date_str)
        elif "Contact:" in line:
            transaction["contact"] = line.split(":", 1)[1].strip()
        elif "Type:" in line:
            transaction["type"] = line.split(":", 1)[1].strip()
        elif "Status:" in line:
            transaction["status"] = line.split(":", 1)[1].strip()
        elif "Reference:" in line:
            transaction["reference"] = line.split(":", 1)[1].strip()
        elif "Line Amount:" in line or "Amount:" in line:
            try:
                amount_str = line.split(":", 1)[1].strip()
                amount = float(re.sub(r'[^\d.-]', '', amount_str))
                current_item["amount"] = amount
            except (ValueError, IndexError):
                pass
        elif "Description:" in line:
            if "amount" in current_item:
                current_item["description"] = line.split(":", 1)[1].strip()
                transaction["line_items"].append(current_item.copy())
                transaction["total"] += abs(current_item.get("amount", 0))
                current_item = {}
    
    return transaction


@app.get("/manual-journals", response_class=HTMLResponse)
async def manual_journals(request: Request):
    """Display manual journal entries from Xero."""
    try:
        # Get selected connection and tenant using helper function
        selection = await get_selected_connection_and_tenant(
            request,
            software_filter="xero",
            require_tenant=True
        )
        
        if selection["error"]:
            return templates.TemplateResponse(
                "manual-journals.html",
                {
                    "request": request,
                    "error": selection["error"],
                    "connections": selection["selector_data"]["connections"],
                    "categories": selection["selector_data"]["categories"],
                    "selected_connection_ids": [selection["selected_connection"]["id"]] if selection["selected_connection"] else [],
                    "allow_multiple": False,
                    "selected_connection": selection["selected_connection"],
                    "selected_tenant": selection["selected_tenant"],
                    "journals": []
                }
            )
        
        selected_connection = selection["selected_connection"]
        selected_tenant = selection["selected_tenant"]
        access_token = selection["access_token"]
        tenant_id = selection["tenant_id"]
        tenant_name = selection["tenant_name"]
        
        # Check if async mode is requested
        async_param = request.query_params.get("async", "true")
        use_async = async_param.lower() == "true"
        
        if use_async:
            # Generate a unique session ID for progress tracking
            session_id = request.session.get("session_id")
            if not session_id:
                session_id = str(uuid.uuid4())
                request.session["session_id"] = session_id
            
            progress_key = f"journal_progress_{session_id}"
            
            # Check if there's already a result
            if progress_key in _journal_progress:
                progress_data = _journal_progress[progress_key]
                if progress_data["status"] == "complete" and progress_data["data"]:
                    result_data = progress_data["data"]
                    del _journal_progress[progress_key]
                    return templates.TemplateResponse(
                        "manual-journals.html",
                        {
                            "request": request,
                            "journals": result_data["journals"],
                            "error": None,
                            "async_mode": False,
                            "connections": selection["selector_data"]["connections"],
                            "categories": selection["selector_data"]["categories"],
                            "selected_connection_ids": [selected_connection["id"]],
                            "allow_multiple": False,
                            "selected_connection": selected_connection,
                            "selected_tenant": selected_tenant
                        }
                    )
                elif progress_data["status"] == "error":
                    error_msg = progress_data.get("error", "Unknown error")
                    del _journal_progress[progress_key]
                    return templates.TemplateResponse(
                        "manual-journals.html",
                        {
                            "request": request,
                            "journals": [],
                            "error": f"Failed to fetch journals: {error_msg}",
                            "async_mode": False,
                            "connections": selection["selector_data"]["connections"],
                            "categories": selection["selector_data"]["categories"],
                            "selected_connection_ids": [selected_connection["id"]],
                            "allow_multiple": False,
                            "selected_connection": selected_connection,
                            "selected_tenant": selected_tenant
                        }
                    )
            
            # Start background task if not already running
            if progress_key not in _journal_progress or _journal_progress[progress_key]["status"] != "loading":
                asyncio.create_task(_fetch_journals_async(session_id, access_token, tenant_id))
            
            # Return loading page
            return templates.TemplateResponse(
                "manual-journals.html",
                {
                    "request": request,
                    "journals": None,
                    "error": None,
                    "async_mode": True,
                    "session_id": session_id,
                    "connections": selection["selector_data"]["connections"],
                    "categories": selection["selector_data"]["categories"],
                    "selected_connection_ids": [selected_connection["id"]],
                    "allow_multiple": False,
                    "selected_connection": selected_connection,
                    "selected_tenant": selected_tenant
                }
            )
        else:
            # Synchronous mode
            mcp_client = None
            journals = []
            parsed_journals = []
            error = None
            
            try:
                logger.info("Initializing MCP client for manual journals...")
                mcp_client = XeroMCPClient(bearer_token=access_token)
                
                result = await mcp_client.call_tool("list-manual-journals", {})
                if isinstance(result, dict) and "content" in result:
                    logger.info("Processing manual journals content...")
                    journals = await _process_manual_journals_content(
                        result["content"], 
                        mcp_client,
                        access_token=access_token,
                        tenant_id=tenant_id
                    )
                    
                    for item in journals:
                        if item.get("type") == "text":
                            parsed_journal = _parse_manual_journal_text(item.get("text", ""))
                            parsed_journals.append(parsed_journal)
                
                await mcp_client.close()
                mcp_client = None
                
            except Exception as e:
                logger.error(f"Error fetching manual journals: {str(e)}", exc_info=True)
                error = str(e)
                if mcp_client:
                    try:
                        await mcp_client.close()
                    except:
                        pass
            
            return templates.TemplateResponse(
                "manual-journals.html",
                {
                    "request": request,
                    "journals": parsed_journals,
                    "error": error,
                    "async_mode": False,
                    "connections": selection["selector_data"]["connections"],
                    "categories": selection["selector_data"]["categories"],
                    "selected_connection_ids": [selected_connection["id"]],
                    "allow_multiple": False,
                    "selected_connection": selected_connection,
                    "selected_tenant": selected_tenant
                }
            )
    
    except Exception as e:
        logger.error(f"Error in manual-journals route: {str(e)}", exc_info=True)
        selector_data = get_connections_for_selector()
        selected_connection_id = selection["selected_connection"]["id"] if 'selection' in locals() and selection["selected_connection"] else None
        return templates.TemplateResponse(
            "manual-journals.html",
            {
                "request": request,
                "journals": [],
                "error": f"Failed to load journals: {str(e)}",
                "async_mode": False,
                "connections": selector_data["connections"],
                "categories": selector_data["categories"],
                "selected_connection_ids": [selected_connection_id] if selected_connection_id else [],
                "allow_multiple": False,
                "selected_connection": selection["selected_connection"] if 'selection' in locals() and selection["selected_connection"] else None,
                "selected_tenant": selection["selected_tenant"] if 'selection' in locals() and selection["selected_tenant"] else None
            }
        )


@app.get("/bank-transactions", response_class=HTMLResponse)
async def bank_transactions(request: Request):
    """Display bank transactions (bank feeds) from Xero."""
    try:
        # Get selected connection and tenant using helper function
        selection = await get_selected_connection_and_tenant(
            request,
            software_filter="xero",
            require_tenant=True
        )
        
        if selection["error"]:
            return templates.TemplateResponse(
                "bank-transactions.html",
                {
                    "request": request,
                    "error": selection["error"],
                    "connections": selection["selector_data"]["connections"],
                    "categories": selection["selector_data"]["categories"],
                    "selected_connection_ids": [selection["selected_connection"]["id"]] if selection["selected_connection"] else [],
                    "allow_multiple": False,
                    "selected_connection": selection["selected_connection"],
                    "selected_tenant": selection["selected_tenant"],
                    "transactions": []
                }
            )
        
        selected_connection = selection["selected_connection"]
        selected_tenant = selection["selected_tenant"]
        access_token = selection["access_token"]
        tenant_name = selection["tenant_name"]
        
        # Check if async mode is requested
        async_param = request.query_params.get("async", "true")
        use_async = async_param.lower() == "true"
        
        if use_async:
            # Generate a unique session ID for progress tracking
            session_id = request.session.get("session_id")
            if not session_id:
                session_id = str(uuid.uuid4())
                request.session["session_id"] = session_id
            
            progress_key = f"transaction_progress_{session_id}"
            
            # Check if there's already a result
            if progress_key in _transaction_progress:
                progress_data = _transaction_progress[progress_key]
                if progress_data["status"] == "complete" and progress_data["data"]:
                    result_data = progress_data["data"]
                    del _transaction_progress[progress_key]
                    return templates.TemplateResponse(
                        "bank-transactions.html",
                        {
                            "request": request,
                            "transactions": result_data["transactions"],
                            "error": None,
                            "async_mode": False,
                            "connections": selection["selector_data"]["connections"],
                            "categories": selection["selector_data"]["categories"],
                            "selected_connection_ids": [selected_connection["id"]],
                            "allow_multiple": False,
                            "selected_connection": selected_connection,
                            "selected_tenant": selected_tenant
                        }
                    )
                elif progress_data["status"] == "error":
                    error_msg = progress_data.get("error", "Unknown error")
                    del _transaction_progress[progress_key]
                    return templates.TemplateResponse(
                        "bank-transactions.html",
                        {
                            "request": request,
                            "transactions": [],
                            "error": f"Failed to fetch transactions: {error_msg}",
                            "async_mode": False,
                            "connections": selection["selector_data"]["connections"],
                            "categories": selection["selector_data"]["categories"],
                            "selected_connection_ids": [selected_connection["id"]],
                            "allow_multiple": False,
                            "selected_connection": selected_connection,
                            "selected_tenant": selected_tenant
                        }
                    )
            
            # Start background task if not already running
            if progress_key not in _transaction_progress or _transaction_progress[progress_key]["status"] != "loading":
                asyncio.create_task(_fetch_transactions_async(session_id, access_token))
            
            # Return loading page
            return templates.TemplateResponse(
                "bank-transactions.html",
                {
                    "request": request,
                    "transactions": None,
                    "error": None,
                    "async_mode": True,
                    "session_id": session_id,
                    "connections": selection["selector_data"]["connections"],
                    "categories": selection["selector_data"]["categories"],
                    "selected_connection_ids": [selected_connection["id"]],
                    "allow_multiple": False,
                    "selected_connection": selected_connection,
                    "selected_tenant": selected_tenant
                }
            )
        else:
            # Synchronous mode
            mcp_client = None
            transactions = []
            parsed_transactions = []
            error = None
            
            try:
                logger.info("Initializing MCP client for bank transactions...")
                mcp_client = XeroMCPClient(bearer_token=access_token)
                
                result = await mcp_client.call_tool("list-bank-transactions", {"page": 1})
                if isinstance(result, dict) and "content" in result:
                    transactions = result["content"]
                    
                    for item in transactions:
                        if item.get("type") == "text":
                            parsed_transaction = _parse_bank_transaction_text(item.get("text", ""))
                            parsed_transactions.append(parsed_transaction)
                
                await mcp_client.close()
                mcp_client = None
                
            except Exception as e:
                logger.error(f"Error fetching bank transactions: {str(e)}", exc_info=True)
                error = str(e)
                if mcp_client:
                    try:
                        await mcp_client.close()
                    except:
                        pass
            
            return templates.TemplateResponse(
                "bank-transactions.html",
                {
                    "request": request,
                    "transactions": parsed_transactions,
                    "error": error,
                    "async_mode": False,
                    "connections": selection["selector_data"]["connections"],
                    "categories": selection["selector_data"]["categories"],
                    "selected_connection_ids": [selected_connection["id"]],
                    "allow_multiple": False,
                    "selected_connection": selected_connection,
                    "selected_tenant": selected_tenant
                }
            )
    
    except Exception as e:
        logger.error(f"Error in bank-transactions route: {str(e)}", exc_info=True)
        selector_data = get_connections_for_selector()
        selected_connection_id = selection["selected_connection"]["id"] if 'selection' in locals() and selection["selected_connection"] else None
        return templates.TemplateResponse(
            "bank-transactions.html",
            {
                "request": request,
                "transactions": [],
                "error": f"Failed to load transactions: {str(e)}",
                "async_mode": False,
                "connections": selector_data["connections"],
                "categories": selector_data["categories"],
                "selected_connection_ids": [selected_connection_id] if selected_connection_id else [],
                "allow_multiple": False,
                "selected_connection": selection["selected_connection"] if 'selection' in locals() and selection["selected_connection"] else None,
                "selected_tenant": selection["selected_tenant"] if 'selection' in locals() and selection["selected_tenant"] else None
            }
        )


# Work in Progress Routes
@app.get("/financial-health/revenue-concentration-risk", response_class=HTMLResponse)
async def revenue_concentration_risk(request: Request):
    """Revenue Concentration Risk - Work in Progress."""
    return templates.TemplateResponse(
        "work_in_progress.html",
        {
            "request": request,
            "page_title": "Revenue Concentration Risk"
        }
    )


@app.get("/financial-health/margin-drift", response_class=HTMLResponse)
async def margin_drift(request: Request):
    """Margin Drift - Work in Progress."""
    return templates.TemplateResponse(
        "work_in_progress.html",
        {
            "request": request,
            "page_title": "Margin Drift"
        }
    )


@app.get("/cash-flow-advisory/cash-strain", response_class=HTMLResponse)
async def cash_strain(request: Request):
    """Cash Strain - Work in Progress."""
    return templates.TemplateResponse(
        "work_in_progress.html",
        {
            "request": request,
            "page_title": "Cash Strain"
        }
    )


@app.get("/profitability/expense-creep", response_class=HTMLResponse)
async def expense_creep(request: Request):
    """Expense Creep - Work in Progress."""
    return templates.TemplateResponse(
        "work_in_progress.html",
        {
            "request": request,
            "page_title": "Expense Creep"
        }
    )


@app.get("/profitability/customer-profitability", response_class=HTMLResponse)
async def customer_profitability(request: Request):
    """Customer Level Profitability - Work in Progress."""
    return templates.TemplateResponse(
        "work_in_progress.html",
        {
            "request": request,
            "page_title": "Customer Level Profitability"
        }
    )


@app.get("/tax-planning/tax-liability", response_class=HTMLResponse)
async def tax_liability(request: Request):
    """Tax Liability - Work in Progress."""
    return templates.TemplateResponse(
        "work_in_progress.html",
        {
            "request": request,
            "page_title": "Tax Liability"
        }
    )


@app.get("/tax-planning/capital-purchase-timing", response_class=HTMLResponse)
async def capital_purchase_timing(request: Request):
    """Capital Purchase Timing - Work in Progress."""
    return templates.TemplateResponse(
        "work_in_progress.html",
        {
            "request": request,
            "page_title": "Capital Purchase Timing"
        }
    )


if __name__ == "__main__":
    import uvicorn
    # Validate config before starting
    try:
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please set XERO_CLIENT_ID and XERO_CLIENT_SECRET in your .env file")
        exit(1)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)


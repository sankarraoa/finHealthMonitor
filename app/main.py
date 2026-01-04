"""FastAPI application for Xero Chart of Accounts."""
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import secrets
from typing import Optional
import logging
import asyncio

from app.config import config
from app.xero_client import XeroClient
from app.mcp_client import XeroMCPClient

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

# Initialize Xero client
xero_client = XeroClient()


def is_authenticated(request: Request) -> bool:
    """Check if user is authenticated."""
    return "access_token" in request.session and "tenant_id" in request.session


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root endpoint - redirects to login or accounts."""
    if is_authenticated(request):
        return RedirectResponse(url="/accounts")
    return RedirectResponse(url="/login")


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
    """Handle OAuth callback from Xero."""
    # Check for errors
    if error:
        logger.error(f"OAuth error: {error}")
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": f"Authentication failed: {error}"}
        )
    
    # Verify state
    stored_state = request.session.get("oauth_state")
    if not stored_state or stored_state != state:
        logger.error("State mismatch in OAuth callback")
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid state parameter. Please try again."}
        )
    
    if not code:
        logger.error("No authorization code received")
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "No authorization code received"}
        )
    
    try:
        # Exchange code for tokens
        token_response = xero_client.get_access_token(code)
        
        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")
        expires_in = token_response.get("expires_in", 1800)
        
        if not access_token:
            raise ValueError("No access token in response")
        
        # Get connected organizations (tenants)
        connections = xero_client.get_connections(access_token)
        
        if not connections:
            raise ValueError("No Xero organizations connected")
        
        # Store tokens and tenant info in session
        # For simplicity, use the first connected organization
        tenant = connections[0]
        request.session["access_token"] = access_token
        request.session["refresh_token"] = refresh_token
        request.session["tenant_id"] = tenant.get("tenantId")
        request.session["tenant_name"] = tenant.get("tenantName")
        request.session["expires_in"] = expires_in
        
        # Clear OAuth state
        request.session.pop("oauth_state", None)
        
        logger.info(f"Successfully authenticated with Xero organization: {tenant.get('tenantName')}")
        
        return RedirectResponse(url="/accounts")
    
    except Exception as e:
        logger.error(f"Error during token exchange: {str(e)}")
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": f"Authentication failed: {str(e)}"}
        )


@app.get("/accounts", response_class=HTMLResponse)
async def accounts(request: Request):
    """Display chart of accounts."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login")
    
    try:
        access_token = request.session.get("access_token")
        tenant_id = request.session.get("tenant_id")
        tenant_name = request.session.get("tenant_name", "Unknown")
        
        # Fetch accounts from Xero
        accounts_data = xero_client.get_accounts(access_token, tenant_id)
        accounts_list = accounts_data.get("Accounts", [])
        
        # Sort accounts by code
        accounts_list.sort(key=lambda x: x.get("Code", ""))
        
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "accounts": accounts_list,
                "tenant_name": tenant_name,
                "account_count": len(accounts_list)
            }
        )
    
    except Exception as e:
        logger.error(f"Error fetching accounts: {str(e)}")
        # If token expired, try to refresh
        if "401" in str(e) or "Unauthorized" in str(e):
            refresh_token = request.session.get("refresh_token")
            if refresh_token:
                try:
                    token_response = xero_client.refresh_token(refresh_token)
                    request.session["access_token"] = token_response.get("access_token")
                    request.session["refresh_token"] = token_response.get("refresh_token")
                    # Retry fetching accounts
                    return RedirectResponse(url="/accounts")
                except Exception as refresh_error:
                    logger.error(f"Token refresh failed: {str(refresh_error)}")
        
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": f"Failed to fetch accounts: {str(e)}",
                "accounts": [],
                "tenant_name": request.session.get("tenant_name", "Unknown"),
                "account_count": 0
            }
        )


@app.get("/invoices", response_class=HTMLResponse)
async def invoices(request: Request):
    """Display outstanding invoices using MCP server."""
    logger.info("Invoices endpoint called")
    
    if not is_authenticated(request):
        logger.warning("Unauthenticated request to /invoices, redirecting to login")
        return RedirectResponse(url="/login")
    
    access_token = request.session.get("access_token")
    tenant_id = request.session.get("tenant_id")
    tenant_name = request.session.get("tenant_name", "Unknown")
    
    logger.info(f"Fetching invoices for tenant: {tenant_name} (ID: {tenant_id})")
    logger.debug(f"Access token present: {bool(access_token)}")
    
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
                "tenant_name": tenant_name,
                "invoice_count": len(invoices_list),
                "total_outstanding": total_outstanding
            }
        )
    
    except Exception as e:
        logger.error(f"Error fetching invoices via MCP: {str(e)}", exc_info=True)
        
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
                "error": f"Failed to fetch invoices: {str(e)}",
                "invoices": [],
                "tenant_name": request.session.get("tenant_name", "Unknown"),
                "invoice_count": 0,
                "total_outstanding": 0
            }
        )


@app.get("/logout")
async def logout(request: Request):
    """Clear session and logout."""
    request.session.clear()
    return RedirectResponse(url="/login")


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


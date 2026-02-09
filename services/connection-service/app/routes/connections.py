"""Connection management and OAuth routes."""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import secrets
import logging

from app.database import get_db
from app.services.connection_service import ConnectionService
from app.schemas.connection import (
    ConnectionCreate,
    ConnectionUpdate,
    ConnectionResponse,
    TenantCreate
)
from app.clients.xero_client import XeroClient
from app.clients.quickbooks_client import QuickBooksClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/connections", tags=["connections"])

connection_service = ConnectionService()
xero_client = XeroClient()
quickbooks_client = QuickBooksClient()


@router.get("", response_model=List[ConnectionResponse])
async def list_connections(
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    db: Session = Depends(get_db)
):
    """List all connections, optionally filtered by tenant_id."""
    connections = connection_service.get_all_connections(tenant_id=tenant_id)
    return connections


@router.get("/{connection_id}", response_model=ConnectionResponse)
async def get_connection(
    connection_id: str,
    tenant_id: Optional[str] = Query(None, description="Verify connection belongs to tenant"),
    db: Session = Depends(get_db)
):
    """Get a specific connection by ID."""
    connection = connection_service.get_connection(connection_id, tenant_id=tenant_id)
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    return connection


@router.post("", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_connection(
    connection_data: ConnectionCreate,
    db: Session = Depends(get_db)
):
    """Create a new connection."""
    connection_id = connection_service.create_connection(
        category=connection_data.category,
        software=connection_data.software,
        name=connection_data.name,
        access_token=connection_data.access_token,
        refresh_token=connection_data.refresh_token,
        tenant_id=connection_data.tenant_id,
        expires_in=connection_data.expires_in,
        metadata=connection_data.metadata,
        tenants=connection_data.tenants
    )
    connection = connection_service.get_connection(connection_id)
    return connection


@router.put("/{connection_id}", response_model=ConnectionResponse)
async def update_connection(
    connection_id: str,
    connection_data: ConnectionUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing connection."""
    success = connection_service.update_connection(
        connection_id=connection_id,
        name=connection_data.name,
        access_token=connection_data.access_token,
        refresh_token=connection_data.refresh_token,
        expires_in=connection_data.expires_in,
        metadata=connection_data.metadata,
        tenants=connection_data.tenants
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    connection = connection_service.get_connection(connection_id)
    return connection


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: str,
    db: Session = Depends(get_db)
):
    """Delete a connection."""
    success = connection_service.delete_connection(connection_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    return None


@router.get("/{connection_id}/connect")
async def initiate_oauth(
    connection_id: str,
    software: str = Query(..., description="Software type: xero or quickbooks"),
    db: Session = Depends(get_db)
):
    """Initiate OAuth flow for a connection."""
    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)
    
    # Store state in connection metadata (or use session/redis in production)
    connection = connection_service.get_connection(connection_id)
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    
    # Update metadata with state
    metadata = connection.get("metadata", {})
    metadata["oauth_state"] = state
    connection_service.update_connection(connection_id, metadata=metadata)
    
    # Get authorization URL based on software
    if software.lower() == "xero":
        auth_url = xero_client.get_authorization_url(state=state)
    elif software.lower() == "quickbooks":
        auth_url = quickbooks_client.get_authorization_url(state=state)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported software: {software}")
    
    return RedirectResponse(url=auth_url)


@router.get("/{connection_id}/callback")
async def oauth_callback(
    connection_id: str,
    code: str = Query(..., description="Authorization code from OAuth provider"),
    state: Optional[str] = Query(None, description="State parameter for CSRF protection"),
    software: Optional[str] = Query(None, description="Software type: xero or quickbooks"),
    db: Session = Depends(get_db)
):
    """Handle OAuth callback and create/update connection."""
    # Verify state
    connection = connection_service.get_connection(connection_id)
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    
    stored_state = connection.get("metadata", {}).get("oauth_state")
    if state and stored_state and state != stored_state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state parameter")
    
    # Determine software from connection if not provided
    if not software:
        software = connection.get("software", "xero")
    
    # Exchange code for tokens
    try:
        if software.lower() == "xero":
            token_response = xero_client.get_access_token(code)
            # Get connected organizations
            access_token = token_response.get("access_token")
            xero_connections = xero_client.get_connections(access_token)
            
            # Build tenants list
            tenants = []
            for xero_conn in xero_connections:
                tenants.append({
                    "tenant_id": xero_conn.get("tenantId"),
                    "tenant_name": xero_conn.get("tenantName", ""),
                    "xero_connection_id": xero_conn.get("id")
                })
        elif software.lower() == "quickbooks":
            token_response = quickbooks_client.get_access_token(code)
            tenants = []  # QuickBooks handles tenants differently
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported software: {software}")
        
        # Update connection with tokens and tenants
        connection_service.update_connection(
            connection_id=connection_id,
            access_token=token_response.get("access_token"),
            refresh_token=token_response.get("refresh_token"),
            expires_in=token_response.get("expires_in", 1800),
            tenants=tenants if tenants else None
        )
        
        # Remove state from metadata
        metadata = connection.get("metadata", {})
        metadata.pop("oauth_state", None)
        connection_service.update_connection(connection_id, metadata=metadata)
        
        return JSONResponse({
            "status": "success",
            "connection_id": connection_id,
            "message": "Connection authorized successfully"
        })
    except Exception as e:
        logger.error(f"Error in OAuth callback: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{connection_id}/refresh")
async def refresh_token(
    connection_id: str,
    db: Session = Depends(get_db)
):
    """Refresh an expired access token."""
    connection = connection_service.get_connection(connection_id)
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    
    refresh_token_value = connection.get("refresh_token")
    if not refresh_token_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No refresh token available")
    
    software = connection.get("software", "xero")
    
    try:
        if software.lower() == "xero":
            token_response = xero_client.refresh_token(refresh_token_value)
        elif software.lower() == "quickbooks":
            token_response = quickbooks_client.refresh_token(refresh_token_value)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported software: {software}")
        
        # Update connection with new tokens
        connection_service.update_connection(
            connection_id=connection_id,
            access_token=token_response.get("access_token"),
            refresh_token=token_response.get("refresh_token", refresh_token_value),  # Keep old if not provided
            expires_in=token_response.get("expires_in", 1800)
        )
        
        return JSONResponse({
            "status": "success",
            "message": "Token refreshed successfully"
        })
    except Exception as e:
        logger.error(f"Error refreshing token: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{connection_id}/tenants", status_code=status.HTTP_201_CREATED)
async def add_tenant(
    connection_id: str,
    tenant_data: TenantCreate,
    db: Session = Depends(get_db)
):
    """Add a tenant to a connection."""
    success = connection_service.add_tenant(
        connection_id=connection_id,
        tenant_id=tenant_data.tenant_id,
        tenant_name=tenant_data.tenant_name,
        xero_connection_id=tenant_data.xero_connection_id
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to add tenant (may already exist)")
    return JSONResponse({"status": "success", "message": "Tenant added successfully"})


@router.delete("/{connection_id}/tenants/{tenant_id}")
async def remove_tenant(
    connection_id: str,
    tenant_id: str,
    db: Session = Depends(get_db)
):
    """Remove a tenant from a connection."""
    success = connection_service.remove_tenant(connection_id, tenant_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return JSONResponse({"status": "success", "message": "Tenant removed successfully"})


@router.get("/{connection_id}/tenants", response_model=List[dict])
async def list_tenants(
    connection_id: str,
    db: Session = Depends(get_db)
):
    """Get all tenants for a connection."""
    tenants = connection_service.get_all_tenants_for_connection(connection_id)
    return tenants

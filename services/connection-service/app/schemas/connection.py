"""Pydantic schemas for connection management."""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class TenantResponse(BaseModel):
    """Xero/QuickBooks tenant response."""
    tenant_id: str
    tenant_name: str
    xero_connection_id: Optional[str] = None


class ConnectionResponse(BaseModel):
    """Connection response schema."""
    id: str
    tenant_id: Optional[str] = None
    category: str
    software: str
    name: str
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: int
    token_created_at: Optional[str] = None
    created_at: str
    updated_at: str
    metadata: Dict[str, Any] = {}
    tenants: List[TenantResponse] = []

    class Config:
        from_attributes = True


class ConnectionCreate(BaseModel):
    """Schema for creating a connection."""
    category: str
    software: str
    name: str
    access_token: str
    refresh_token: Optional[str] = None
    tenant_id: Optional[str] = None
    expires_in: int = 1800
    metadata: Optional[Dict[str, Any]] = None
    tenants: Optional[List[Dict[str, Any]]] = None


class ConnectionUpdate(BaseModel):
    """Schema for updating a connection."""
    name: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    tenants: Optional[List[Dict[str, Any]]] = None


class TenantCreate(BaseModel):
    """Schema for adding a tenant to a connection."""
    tenant_id: str
    tenant_name: str
    xero_connection_id: Optional[str] = None

"""Tenant management routes."""
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.services import tenant_service, role_service, permission_service
from app.schemas.rbac import TenantCreate, TenantResponse
from app.routes.dependencies import get_current_user_id, get_current_tenant_id

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant_data: TenantCreate,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Create a new tenant (customer company)."""
    # Check if tenant already exists
    existing = tenant_service.get_tenant_by_name(db, tenant_data.company_name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant with this name already exists"
        )
    
    # Get parent_tenant_id and created_by from JWT token
    parent_tenant_id = await get_current_tenant_id(authorization)
    created_by = await get_current_user_id(authorization)
    
    tenant = tenant_service.create_tenant(
        db,
        company_name=tenant_data.company_name,
        tax_id=tenant_data.tax_id,
        phone=tenant_data.phone,
        email=tenant_data.email,
        parent_tenant_id=parent_tenant_id,
        created_by=created_by
    )
    
    # Create default roles for tenant
    role_service.create_default_roles_for_tenant(db, tenant.id, permission_service, created_by=created_by)
    
    return tenant


@router.get("", response_model=List[TenantResponse])
async def list_tenants(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all tenants."""
    return tenant_service.list_tenants(db, skip=skip, limit=limit)


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    db: Session = Depends(get_db)
):
    """Get tenant by ID."""
    tenant = tenant_service.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    return tenant

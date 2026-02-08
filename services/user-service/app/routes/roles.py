"""Role management routes."""
from fastapi import APIRouter, Depends, HTTPException, status, Header, Response
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.services import role_service, tenant_service, permission_service
from app.schemas.rbac import RoleCreate, RoleResponse, PermissionResponse, AssignPermissionToRole
from app.routes.dependencies import get_current_user_id, get_current_tenant_id

router = APIRouter(prefix="/api", tags=["roles"])


@router.get("/tenants/{tenant_id}/roles/{role_id}", response_model=RoleResponse)
async def get_role_in_tenant(
    tenant_id: str,
    role_id: str,
    db: Session = Depends(get_db)
):
    """Get a single role by ID within a tenant."""
    tenant = tenant_service.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    role = role_service.get_role_by_id(db, role_id)
    if not role or role.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found in this tenant"
        )
    
    return role


@router.get("/tenants/{tenant_id}/roles", response_model=List[RoleResponse])
async def list_roles_in_tenant(
    tenant_id: str,
    db: Session = Depends(get_db)
):
    """List all roles in a tenant."""
    tenant = tenant_service.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    return role_service.list_roles_in_tenant(db, tenant_id)


@router.post("/tenants/{tenant_id}/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role_in_tenant(
    tenant_id: str,
    role_data: RoleCreate,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Create a new role in a tenant."""
    tenant = tenant_service.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    # Check if role already exists
    existing = role_service.get_role_by_name(db, tenant_id, role_data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role with this name already exists in tenant"
        )
    
    # Get created_by from JWT token
    created_by = await get_current_user_id(authorization)
    
    return role_service.create_role(
        db,
        tenant_id=tenant_id,
        name=role_data.name,
        description=role_data.description,
        created_by=created_by
    )


@router.get("/tenants/{tenant_id}/roles/{role_id}/permissions", response_model=List[PermissionResponse])
async def get_role_permissions(
    tenant_id: str,
    role_id: str,
    db: Session = Depends(get_db)
):
    """Get all permissions for a role."""
    role = role_service.get_role_by_id(db, role_id)
    if not role or role.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    return role_service.get_role_permissions(db, role_id)


@router.post("/tenants/{tenant_id}/roles/{role_id}/permissions", status_code=status.HTTP_201_CREATED, response_model=PermissionResponse)
async def assign_permission_to_role(
    tenant_id: str,
    role_id: str,
    data: AssignPermissionToRole,
    db: Session = Depends(get_db)
):
    """Assign a permission to a role."""
    role = role_service.get_role_by_id(db, role_id)
    if not role or role.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    permission = permission_service.get_permission_by_id(db, data.permission_id)
    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission not found"
        )
    
    role_service.assign_permission_to_role(db, role_id, data.permission_id)
    permission = permission_service.get_permission_by_id(db, data.permission_id)
    return permission


@router.delete("/tenants/{tenant_id}/roles/{role_id}/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_permission_from_role(
    tenant_id: str,
    role_id: str,
    permission_id: str,
    db: Session = Depends(get_db)
):
    """Remove a permission from a role."""
    role = role_service.get_role_by_id(db, role_id)
    if not role or role.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    success = role_service.remove_permission_from_role(db, role_id, permission_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission not found in role"
        )
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)

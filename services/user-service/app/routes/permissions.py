"""Permission management routes."""
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from typing import List, Optional, Dict

from app.database import get_db
from app.services import permission_service
from app.schemas.rbac import PermissionCreate, PermissionResponse
from app.routes.dependencies import get_current_user_id, get_current_tenant_id

router = APIRouter(prefix="/api/permissions", tags=["permissions"])


@router.get("/by-resource", response_model=dict)
async def list_permissions_by_resource(
    db: Session = Depends(get_db)
):
    """List permissions grouped by resource."""
    permissions_dict = permission_service.list_permissions_by_resource(db)
    return {
        resource: [
            {
                "id": perm.id,
                "resource": perm.resource,
                "action": perm.action,
                "description": perm.description
            }
            for perm in perms
        ]
        for resource, perms in permissions_dict.items()
    }


@router.get("", response_model=List[PermissionResponse])
async def list_permissions(
    skip: int = 0,
    limit: int = 1000,
    db: Session = Depends(get_db)
):
    """List all permissions."""
    return permission_service.list_permissions(db, skip=skip, limit=limit)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PermissionResponse)
async def create_permission(
    data: PermissionCreate,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Create a new permission."""
    # Check if permission already exists
    existing = permission_service.get_permission_by_resource_action(db, data.resource, data.action)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Permission with this resource and action already exists"
        )
    
    # Get tenant_id and created_by from JWT token
    tenant_id = await get_current_tenant_id(authorization)
    created_by = await get_current_user_id(authorization)
    
    return permission_service.create_permission(
        db,
        resource=data.resource,
        action=data.action,
        description=data.description,
        tenant_id=tenant_id,
        created_by=created_by
    )


@router.get("/{permission_id}", response_model=PermissionResponse)
async def get_permission(
    permission_id: str,
    db: Session = Depends(get_db)
):
    """Get a single permission by ID."""
    permission = permission_service.get_permission_by_id(db, permission_id)
    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission not found"
        )
    return permission

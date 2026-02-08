"""User management routes."""
from fastapi import APIRouter, Depends, HTTPException, status, Header, Response
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.services import user_service, tenant_service, role_service
from app.schemas.rbac import UserCreate, UserUpdate, UserResponse
from app.models.rbac import UserTenantRole, TenantRole
from app.routes.dependencies import get_current_user_id

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/tenants/{tenant_id}/users", response_model=List[dict])
async def list_users_in_tenant(
    tenant_id: str,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all users in a tenant with their roles."""
    tenant = tenant_service.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    users = user_service.list_users_in_tenant(db, tenant_id, skip=skip, limit=limit)
    
    # Get roles for each user
    result = []
    for user in users:
        # Get user's roles in this tenant
        memberships = db.query(UserTenantRole).filter(
            UserTenantRole.user_id == user.id,
            UserTenantRole.tenant_id == tenant_id
        ).all()
        
        role_ids = [m.role_id for m in memberships]
        roles = db.query(TenantRole).filter(TenantRole.id.in_(role_ids)).all() if role_ids else []
        
        result.append({
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
            "phone": user.phone,
            "image_url": user.image_url,
            "is_active": user.is_active,
            "roles": [{"id": r.id, "name": r.name, "description": r.description} for r in roles]
        })
    
    return result


@router.get("/tenants/{tenant_id}/users/{user_id}", response_model=UserResponse)
async def get_user_in_tenant(
    tenant_id: str,
    user_id: str,
    db: Session = Depends(get_db)
):
    """Get a single user by ID within a tenant."""
    tenant = tenant_service.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    user = user_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Verify user is in this tenant
    user_tenants = user_service.get_user_tenants(db, user_id)
    if not any(t.id == tenant_id for t in user_tenants):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in this tenant"
        )
    
    return user


@router.put("/tenants/{tenant_id}/users/{user_id}", response_model=UserResponse)
async def update_user_in_tenant(
    tenant_id: str,
    user_id: str,
    user_data: UserUpdate,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Update a user in a tenant."""
    tenant = tenant_service.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    user = user_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Verify user is in tenant
    membership = db.query(UserTenantRole).filter(
        UserTenantRole.user_id == user_id,
        UserTenantRole.tenant_id == tenant_id
    ).first()
    
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in this tenant"
        )
    
    # Get modified_by from JWT token
    modified_by = await get_current_user_id(authorization)
    
    updated_user = user_service.update_user(
        db,
        user_id,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        phone=user_data.phone,
        image_url=user_data.image_url,
        password=user_data.password,
        modified_by=modified_by
    )
    
    return updated_user


@router.get("/tenants/{tenant_id}/users/{user_id}/roles", response_model=List[dict])
async def get_user_roles(
    tenant_id: str,
    user_id: str,
    db: Session = Depends(get_db)
):
    """Get all roles assigned to a user in a tenant."""
    tenant = tenant_service.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    user = user_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Get user's roles in this tenant
    memberships = db.query(UserTenantRole).filter(
        UserTenantRole.user_id == user_id,
        UserTenantRole.tenant_id == tenant_id
    ).all()
    
    role_ids = [m.role_id for m in memberships]
    roles = db.query(TenantRole).filter(TenantRole.id.in_(role_ids)).all()
    
    return [{"id": r.id, "name": r.name, "description": r.description, "is_system_role": r.is_system_role} for r in roles]


@router.post("/tenants/{tenant_id}/users/{user_id}/roles/{role_id}", status_code=status.HTTP_201_CREATED)
async def assign_role_to_user(
    tenant_id: str,
    user_id: str,
    role_id: str,
    db: Session = Depends(get_db)
):
    """Assign a role to a user in a tenant."""
    tenant = tenant_service.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    user = user_service.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    role = role_service.get_role_by_id(db, role_id)
    if not role or role.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found in this tenant"
        )
    
    # Check if already assigned
    existing = db.query(UserTenantRole).filter(
        UserTenantRole.user_id == user_id,
        UserTenantRole.tenant_id == tenant_id,
        UserTenantRole.role_id == role_id
    ).first()
    
    if existing:
        return {"message": "Role already assigned", "id": existing.id}
    
    membership = user_service.add_user_to_tenant(db, user_id, tenant_id, role_id)
    return {"message": "Role assigned", "id": membership.id}


@router.delete("/tenants/{tenant_id}/users/{user_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_role_from_user(
    tenant_id: str,
    user_id: str,
    role_id: str,
    db: Session = Depends(get_db)
):
    """Remove a role from a user in a tenant."""
    membership = db.query(UserTenantRole).filter(
        UserTenantRole.user_id == user_id,
        UserTenantRole.tenant_id == tenant_id,
        UserTenantRole.role_id == role_id
    ).first()
    
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role assignment not found"
        )
    
    db.delete(membership)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/tenants/{tenant_id}/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def add_user_to_tenant(
    tenant_id: str,
    user_data: UserCreate,
    role_id: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Add a user to a tenant. Creates user if doesn't exist."""
    tenant = tenant_service.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    # Get created_by from JWT token
    current_user_id = await get_current_user_id(authorization)
    session_tenant_id = await get_current_tenant_id(authorization)
    
    # Get or create user
    user = user_service.get_user_by_email(db, user_data.email)
    if not user:
        user = user_service.create_user(
            db,
            email=user_data.email,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            password=user_data.password,
            phone=user_data.phone,
            tenant_id=session_tenant_id or tenant_id,
            created_by=current_user_id
        )
    
    # Get default role if not provided
    if not role_id:
        admin_role = role_service.get_role_by_name(db, tenant_id, "Administrator")
        if not admin_role:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Default role not found in tenant"
            )
        role_id = admin_role.id
    
    # Add user to tenant
    user_service.add_user_to_tenant(db, user.id, tenant_id, role_id, assigned_by=current_user_id)
    
    return user

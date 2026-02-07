"""RBAC API routes."""
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.auth.dependencies import get_current_user, get_current_tenant, require_tenant_membership
from app.models.party import Person, Organization
from app.models.rbac import UserTenantRole, TenantRole
from app.services import tenant_service, user_service, role_service, permission_service

router = APIRouter(prefix="/api", tags=["rbac"])


# Pydantic models for request/response
class TenantCreate(BaseModel):
    company_name: str
    tax_id: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class TenantResponse(BaseModel):
    id: str
    company_name: str
    tax_id: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    is_active: bool
    
    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    password: Optional[str] = None
    phone: Optional[str] = None
    image_url: Optional[str] = None


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    image_url: Optional[str] = None
    password: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    full_name: str
    phone: Optional[str]
    image_url: Optional[str]
    is_active: bool
    
    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None


class RoleResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: Optional[str]
    is_system_role: str
    
    class Config:
        from_attributes = True


class PermissionCreate(BaseModel):
    resource: str
    action: str
    description: Optional[str] = None


class PermissionResponse(BaseModel):
    id: str
    resource: str
    action: str
    description: Optional[str]
    
    class Config:
        from_attributes = True


class AssignRoleToUser(BaseModel):
    role_id: str


class AssignPermissionToRole(BaseModel):
    permission_id: str


# Authentication routes
@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    tenant_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Register a new user. If tenant_id is provided, user is added to that tenant."""
    # Check if user already exists
    existing_user = user_service.get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )
    
    # Create user
    user = user_service.create_user(
        db,
        email=user_data.email,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        password=user_data.password,
        phone=user_data.phone
    )
    
    # If tenant_id provided, add user to tenant with default role (or create tenant)
    if tenant_id:
        tenant = tenant_service.get_tenant_by_id(db, tenant_id)
        if tenant:
            # Get or create default role (Administrator)
            admin_role = role_service.get_role_by_name(db, tenant_id, "Administrator")
            if admin_role:
                user_service.add_user_to_tenant(db, user.id, tenant_id, admin_role.id)
    
    return user


@router.post("/auth/login", response_model=dict)
async def login_user(
    credentials: UserLogin,
    db: Session = Depends(get_db)
):
    """Login user with email and password."""
    user = user_service.authenticate_user(db, credentials.email, credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Get user's tenants
    tenants = user_service.get_user_tenants(db, user.id)
    
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name
        },
        "tenants": [
            {
                "id": t.id,
                "company_name": t.company_name
            }
            for t in tenants
        ]
    }


# Tenant routes
@router.post("/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant_data: TenantCreate,
    db: Session = Depends(get_db)
):
    """Create a new tenant organization."""
    # Check if tenant already exists
    existing = tenant_service.get_tenant_by_name(db, tenant_data.company_name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant with this name already exists"
        )
    
    tenant = tenant_service.create_tenant(
        db,
        company_name=tenant_data.company_name,
        tax_id=tenant_data.tax_id,
        phone=tenant_data.phone,
        email=tenant_data.email
    )
    
    # Create default roles for tenant
    role_service.create_default_roles_for_tenant(db, tenant.id, permission_service)
    
    return tenant


@router.get("/tenants", response_model=List[TenantResponse])
async def list_tenants(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all tenants."""
    return tenant_service.list_tenants(db, skip=skip, limit=limit)


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
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


# User routes
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
    
    updated_user = user_service.update_user(
        db,
        user_id,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        phone=user_data.phone,
        image_url=user_data.image_url,
        password=user_data.password
    )
    
    return updated_user


@router.get("/tenants/{tenant_id}/users/{user_id}/roles", response_model=List[RoleResponse])
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
    
    return roles


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
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Add a user to a tenant. Creates user if doesn't exist."""
    from app.auth.session import get_current_user_id
    
    tenant = tenant_service.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    # Get current user if authenticated (optional)
    current_user_id = None
    try:
        current_user_id = get_current_user_id(request) if request else None
    except:
        pass  # Not authenticated, which is OK for this endpoint
    
    # Get or create user
    user = user_service.get_user_by_email(db, user_data.email)
    if not user:
        user = user_service.create_user(
            db,
            email=user_data.email,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            password=user_data.password,
            phone=user_data.phone
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


# Role routes
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
    
    return role_service.create_role(
        db,
        tenant_id=tenant_id,
        name=role_data.name,
        description=role_data.description
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
    
    role_permission = role_service.assign_permission_to_role(db, role_id, data.permission_id)
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


# Permission routes
# IMPORTANT: More specific routes must come before parameterized routes
@router.get("/permissions/by-resource", response_model=dict)
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


@router.get("/permissions", response_model=List[PermissionResponse])
async def list_permissions(
    skip: int = 0,
    limit: int = 1000,
    db: Session = Depends(get_db)
):
    """List all permissions."""
    return permission_service.list_permissions(db, skip=skip, limit=limit)


@router.post("/permissions", status_code=status.HTTP_201_CREATED, response_model=PermissionResponse)
async def create_permission(
    data: PermissionCreate,
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
    
    return permission_service.create_permission(db, data)


@router.get("/permissions/{permission_id}", response_model=PermissionResponse)
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

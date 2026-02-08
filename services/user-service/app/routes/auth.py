"""Authentication routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.services import user_service
from app.schemas.rbac import UserLogin, UserCreate, LoginResponse, UserResponse
from app.auth.jwt import create_access_token
from app.models.rbac import UserTenantRole, TenantRole

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
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
        phone=user_data.phone,
        tenant_id=tenant_id,
        created_by=None  # No creator for self-registration
    )
    
    # If tenant_id provided, add user to tenant with default role
    if tenant_id:
        from app.services import tenant_service, role_service
        tenant = tenant_service.get_tenant_by_id(db, tenant_id)
        if tenant:
            # Get or create default role (Administrator)
            admin_role = role_service.get_role_by_name(db, tenant_id, "Administrator")
            if admin_role:
                user_service.add_user_to_tenant(db, user.id, tenant_id, admin_role.id)
    
    return user


@router.post("/login", response_model=LoginResponse)
async def login_user(
    credentials: UserLogin,
    db: Session = Depends(get_db)
):
    """Login user with email and password. Returns JWT token."""
    user = user_service.authenticate_user(db, credentials.email, credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Get user's tenants
    tenants = user_service.get_user_tenants(db, user.id)
    
    # Set default tenant (first one, or getGo if available)
    default_tenant = None
    if tenants:
        # Prefer getGo if available
        getgo_tenant = next((t for t in tenants if t.company_name.lower() == "getgo"), None)
        default_tenant = getgo_tenant if getgo_tenant else tenants[0]
    
    # Get user's role in default tenant (if available)
    role_name = None
    if default_tenant:
        membership = db.query(UserTenantRole).filter(
            UserTenantRole.user_id == user.id,
            UserTenantRole.tenant_id == default_tenant.id
        ).first()
        if membership:
            role = db.query(TenantRole).filter(TenantRole.id == membership.role_id).first()
            if role:
                role_name = role.name
    
    # Create JWT token
    access_token = create_access_token(
        user_id=user.id,
        tenant_id=default_tenant.id if default_tenant else None,
        email=user.email,
        role=role_name
    )
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=user.full_name,
            phone=user.phone,
            image_url=user.image_url,
            is_active=user.is_active
        ),
        tenants=[
            {
                "id": t.id,
                "company_name": t.company_name,
                "tax_id": t.tax_id,
                "phone": t.phone,
                "email": t.email,
                "is_active": t.is_active
            }
            for t in tenants
        ],
        default_tenant={
            "id": default_tenant.id,
            "company_name": default_tenant.company_name,
            "tax_id": default_tenant.tax_id,
            "phone": default_tenant.phone,
            "email": default_tenant.email,
            "is_active": default_tenant.is_active
        } if default_tenant else None
    )

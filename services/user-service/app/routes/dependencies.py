"""FastAPI dependencies for authentication and authorization."""
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.party import Person, Tenant
from app.auth.jwt import verify_token, get_user_id_from_token, get_tenant_id_from_token
from app.services import user_service, tenant_service


async def get_current_user_id(
    authorization: Optional[str] = Header(None)
) -> Optional[str]:
    """Extract user ID from JWT token in Authorization header."""
    if not authorization:
        return None
    
    try:
        # Extract token from "Bearer <token>"
        if authorization.startswith("Bearer "):
            token = authorization[7:]
            payload = verify_token(token)
            return payload.get("sub")
    except HTTPException:
        return None
    
    return None


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> Person:
    """Get the current authenticated user from JWT token."""
    user_id = await get_current_user_id(authorization)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    user = user_service.get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    return user


async def get_current_tenant_id(
    authorization: Optional[str] = Header(None)
) -> Optional[str]:
    """Extract tenant ID from JWT token in Authorization header."""
    if not authorization:
        return None
    
    try:
        if authorization.startswith("Bearer "):
            token = authorization[7:]
            payload = verify_token(token)
            return payload.get("tenant_id")
    except HTTPException:
        return None
    
    return None


async def get_current_tenant(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> Tenant:
    """Get the current tenant from JWT token."""
    tenant_id = await get_current_tenant_id(authorization)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tenant context set"
        )
    
    tenant = tenant_service.get_tenant_by_id(db, tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found or inactive"
        )
    
    return tenant


async def require_authentication(
    user: Person = Depends(get_current_user)
) -> Person:
    """Dependency to require authentication."""
    return user


async def require_tenant_membership(
    user: Person = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> tuple[Person, Tenant]:
    """Dependency to require user belongs to tenant."""
    from app.models.rbac import UserTenantRole
    
    # Check if user belongs to tenant
    membership = db.query(UserTenantRole).filter(
        UserTenantRole.user_id == user.id,
        UserTenantRole.tenant_id == tenant.id
    ).first()
    
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to this tenant"
        )
    
    return user, tenant

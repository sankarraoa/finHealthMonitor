"""FastAPI dependencies for authentication and authorization."""
from fastapi import Depends, Request, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.party import Person, Organization
from app.auth.session import get_current_user_id, get_current_tenant_id


async def get_current_user(request: Request, db: Session = Depends(get_db)) -> Person:
    """Get the current authenticated user."""
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    user = db.query(Person).filter(Person.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    return user


async def get_current_tenant(request: Request, db: Session = Depends(get_db)) -> Organization:
    """Get the current tenant from session."""
    tenant_id = get_current_tenant_id(request)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tenant context set"
        )
    
    tenant = db.query(Organization).filter(Organization.id == tenant_id).first()
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
    tenant: Organization = Depends(get_current_tenant),
    db: Session = Depends(get_db)
) -> tuple[Person, Organization]:
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

"""FastAPI dependencies for authentication and authorization."""
from fastapi import Depends, Request, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.party import Person, Tenant
from app.auth.session import get_current_user_id, get_current_tenant_id, get_current_tenant_id_from_session


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


async def get_current_tenant(request: Request, db: Session = Depends(get_db)) -> Tenant:
    """Get the current tenant from session."""
    tenant_id = get_current_tenant_id(request)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tenant context set"
        )
    
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
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


async def get_current_tenant_id_dep(request: Request) -> str:
    """Dependency to get current tenant ID from session. Raises error if not set."""
    tenant_id = get_current_tenant_id(request)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No tenant context set. Please log in."
        )
    return tenant_id


def get_session_context(request: Request) -> tuple[Optional[str], Optional[str]]:
    """
    Get tenant_id and person_id from session.
    
    Returns:
        Tuple of (tenant_id, person_id). Both can be None if not in session.
    """
    from app.auth.session import get_current_tenant_id, get_current_user_id
    tenant_id = get_current_tenant_id(request)
    person_id = get_current_user_id(request)
    return tenant_id, person_id


async def get_session_context_dep(request: Request) -> tuple[str, str]:
    """
    Dependency to get tenant_id and person_id from session. Raises error if not set.
    
    Returns:
        Tuple of (tenant_id, person_id)
    """
    tenant_id, person_id = get_session_context(request)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No tenant context set. Please log in."
        )
    if not person_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please log in."
        )
    return tenant_id, person_id

"""Session management utilities."""
from fastapi import Request
from typing import Optional
from app.models.party import Person, Organization


def create_user_session(request: Request, user: Person, tenant: Optional[Organization] = None):
    """Create a user session with optional tenant context."""
    request.session["user_id"] = user.id
    request.session["user_email"] = user.email
    if tenant:
        request.session["tenant_id"] = tenant.id
        request.session["tenant_name"] = tenant.company_name


def get_current_user_id(request: Request) -> Optional[str]:
    """Get current user ID from session."""
    return request.session.get("user_id")


def get_current_tenant_id(request: Request) -> Optional[str]:
    """Get current tenant ID from session."""
    return request.session.get("tenant_id")


def logout_user(request: Request):
    """Clear user session."""
    request.session.pop("user_id", None)
    request.session.pop("user_email", None)
    request.session.pop("tenant_id", None)
    request.session.pop("tenant_name", None)

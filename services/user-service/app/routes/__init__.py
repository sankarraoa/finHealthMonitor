"""API routes for user service."""
from app.routes import auth, users, tenants, roles, permissions

__all__ = [
    "auth",
    "users",
    "tenants",
    "roles",
    "permissions",
]

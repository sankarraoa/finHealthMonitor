"""Service for permission management."""
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from app.models.rbac import Permission
import uuid
from datetime import datetime


def create_permission(
    db: Session,
    resource: str,
    action: str,
    description: Optional[str] = None
) -> Permission:
    """Create a new permission."""
    now = datetime.utcnow().isoformat()
    
    permission = Permission(
        id=str(uuid.uuid4()),
        resource=resource,
        action=action,
        description=description,
        created_at=now,
        updated_at=now
    )
    
    db.add(permission)
    db.commit()
    db.refresh(permission)
    return permission


def get_permission_by_id(db: Session, permission_id: str) -> Optional[Permission]:
    """Get permission by ID."""
    return db.query(Permission).filter(Permission.id == permission_id).first()


def get_permission_by_resource_action(db: Session, resource: str, action: str) -> Optional[Permission]:
    """Get permission by resource and action."""
    return db.query(Permission).filter(
        Permission.resource == resource,
        Permission.action == action
    ).first()


def list_permissions(db: Session, skip: int = 0, limit: int = 1000) -> List[Permission]:
    """List all permissions."""
    return db.query(Permission).offset(skip).limit(limit).all()


def list_permissions_by_resource(db: Session) -> Dict[str, List[Permission]]:
    """List permissions grouped by resource."""
    permissions = db.query(Permission).all()
    result = {}
    for perm in permissions:
        if perm.resource not in result:
            result[perm.resource] = []
        result[perm.resource].append(perm)
    return result


def get_or_create_permission(
    db: Session,
    resource: str,
    action: str,
    description: Optional[str] = None
) -> Permission:
    """Get existing permission or create if it doesn't exist."""
    permission = get_permission_by_resource_action(db, resource, action)
    if permission:
        return permission
    return create_permission(db, resource, action, description)

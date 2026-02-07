"""Service for role management."""
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from app.models.rbac import TenantRole, RolePermission, Permission
from app.models.party import Organization
import uuid
from datetime import datetime


def create_role(
    db: Session,
    tenant_id: str,
    name: str,
    description: Optional[str] = None,
    is_system_role: bool = False
) -> TenantRole:
    """Create a new role in a tenant."""
    now = datetime.utcnow().isoformat()
    
    role = TenantRole(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=name,
        description=description,
        is_system_role='true' if is_system_role else 'false',
        created_at=now,
        updated_at=now
    )
    
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def get_role_by_id(db: Session, role_id: str) -> Optional[TenantRole]:
    """Get role by ID."""
    return db.query(TenantRole).filter(TenantRole.id == role_id).first()


def get_role_by_name(db: Session, tenant_id: str, name: str) -> Optional[TenantRole]:
    """Get role by name in a tenant."""
    return db.query(TenantRole).filter(
        TenantRole.tenant_id == tenant_id,
        TenantRole.name == name
    ).first()


def list_roles_in_tenant(db: Session, tenant_id: str, skip: int = 0, limit: int = 100) -> List[TenantRole]:
    """List all roles in a tenant."""
    return db.query(TenantRole).filter(
        TenantRole.tenant_id == tenant_id
    ).offset(skip).limit(limit).all()


def update_role(
    db: Session,
    role_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None
) -> Optional[TenantRole]:
    """Update role information."""
    role = get_role_by_id(db, role_id)
    if not role:
        return None
    
    if name is not None:
        role.name = name
    if description is not None:
        role.description = description
    
    role.updated_at = datetime.utcnow().isoformat()
    db.commit()
    db.refresh(role)
    return role


def delete_role(db: Session, role_id: str) -> bool:
    """Delete a role (only if not a system role)."""
    role = get_role_by_id(db, role_id)
    if not role:
        return False
    
    if role.is_system_role == 'true':
        return False  # Cannot delete system roles
    
    db.delete(role)
    db.commit()
    return True


def assign_permission_to_role(
    db: Session,
    role_id: str,
    permission_id: str
) -> RolePermission:
    """Assign a permission to a role."""
    now = datetime.utcnow().isoformat()
    
    role_permission = RolePermission(
        id=str(uuid.uuid4()),
        role_id=role_id,
        permission_id=permission_id,
        granted_at=now
    )
    
    db.add(role_permission)
    db.commit()
    db.refresh(role_permission)
    return role_permission


def remove_permission_from_role(db: Session, role_id: str, permission_id: str) -> bool:
    """Remove a permission from a role."""
    role_permission = db.query(RolePermission).filter(
        RolePermission.role_id == role_id,
        RolePermission.permission_id == permission_id
    ).first()
    
    if not role_permission:
        return False
    
    db.delete(role_permission)
    db.commit()
    return True


def get_role_permissions(db: Session, role_id: str) -> List[Permission]:
    """Get all permissions for a role."""
    role_permissions = db.query(RolePermission).filter(
        RolePermission.role_id == role_id
    ).all()
    
    permission_ids = [rp.permission_id for rp in role_permissions]
    return db.query(Permission).filter(Permission.id.in_(permission_ids)).all()


def create_default_roles_for_tenant(
    db: Session,
    tenant_id: str,
    permission_service=None  # Optional, for compatibility
) -> Dict[str, TenantRole]:
    """Create default roles for a new tenant with default permissions."""
    from app.services.permission_service import get_or_create_permission
    
    roles = {}
    
    # Administrator role - all permissions
    admin_role = create_role(db, tenant_id, "Administrator", "Full access to all resources", is_system_role=True)
    roles["Administrator"] = admin_role
    
    # IT Administrator - connections only
    it_admin_role = create_role(db, tenant_id, "IT Administrator", "Manage connections only", is_system_role=True)
    roles["IT Administrator"] = it_admin_role
    
    # Accountant - accounts, invoices, journals, bank transactions
    accountant_role = create_role(db, tenant_id, "Accountant", "Access to accounting resources", is_system_role=True)
    roles["Accountant"] = accountant_role
    
    # Controller - payroll risk and cash strain
    controller_role = create_role(db, tenant_id, "Controller", "Access to payroll risk and cash strain", is_system_role=True)
    roles["Controller"] = controller_role
    
    # Finance Executive - view only on all resources
    executive_role = create_role(db, tenant_id, "Finance Executive", "View-only access to all resources", is_system_role=True)
    roles["Finance Executive"] = executive_role
    
    # Assign permissions to roles
    resources = [
        "connections", "accounts", "invoices", "manual-journals", "bank-transactions",
        "payroll-risk", "cash-strain", "revenue-concentration-risk", "margin-drift",
        "expense-creep", "customer-profitability", "tax-liability", "capital-purchase-timing",
        "dashboard", "favorites"
    ]
    actions = ["view", "create", "edit", "delete", "manage"]
    
    # Create all permissions
    permissions = {}
    for resource in resources:
        for action in actions:
            perm = get_or_create_permission(db, resource, action)
            permissions[f"{resource}:{action}"] = perm
    
    # Administrator: all permissions (manage on all)
    for resource in resources:
        perm = permissions.get(f"{resource}:manage")
        if perm:
            assign_permission_to_role(db, admin_role.id, perm.id)
    
    # IT Administrator: connections (manage)
    perm = permissions.get("connections:manage")
    if perm:
        assign_permission_to_role(db, it_admin_role.id, perm.id)
    
    # Accountant: accounts (view, create, edit), invoices (view), manual-journals (view, create, edit), bank-transactions (view)
    for action in ["view", "create", "edit"]:
        perm = permissions.get(f"accounts:{action}")
        if perm:
            assign_permission_to_role(db, accountant_role.id, perm.id)
    perm = permissions.get("invoices:view")
    if perm:
        assign_permission_to_role(db, accountant_role.id, perm.id)
    for action in ["view", "create", "edit"]:
        perm = permissions.get(f"manual-journals:{action}")
        if perm:
            assign_permission_to_role(db, accountant_role.id, perm.id)
    perm = permissions.get("bank-transactions:view")
    if perm:
        assign_permission_to_role(db, accountant_role.id, perm.id)
    
    # Controller: payroll-risk (view, create, edit), cash-strain (view, create, edit)
    for action in ["view", "create", "edit"]:
        perm = permissions.get(f"payroll-risk:{action}")
        if perm:
            assign_permission_to_role(db, controller_role.id, perm.id)
        perm = permissions.get(f"cash-strain:{action}")
        if perm:
            assign_permission_to_role(db, controller_role.id, perm.id)
    
    # Finance Executive: all resources (view only)
    for resource in resources:
        perm = permissions.get(f"{resource}:view")
        if perm:
            assign_permission_to_role(db, executive_role.id, perm.id)
    
    db.commit()
    return roles

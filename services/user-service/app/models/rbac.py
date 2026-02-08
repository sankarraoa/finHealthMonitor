"""RBAC models - Roles, Permissions, and their relationships."""
from sqlalchemy import Column, String, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class Permission(Base):
    """Global permission model - defines resource+action combinations."""
    
    __tablename__ = "permissions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    resource = Column(String(100), nullable=False, index=True)  # e.g., "connections", "payroll-risk"
    action = Column(String(50), nullable=False, index=True)  # e.g., "view", "create", "edit", "delete", "manage"
    description = Column(String(500), nullable=True)
    created_at = Column(String, nullable=False, default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String, nullable=False, default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())
    
    # Relationships
    role_permissions = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('resource', 'action', name='uq_permission_resource_action'),
        Index('idx_permission_resource_action', 'resource', 'action'),
    )
    
    def __repr__(self):
        return f"<Permission(id={self.id}, resource={self.resource}, action={self.action})>"


class TenantRole(Base):
    """Role model scoped to a specific tenant (customer company)."""
    
    __tablename__ = "tenant_roles"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # e.g., "Administrator", "IT Administrator"
    description = Column(String(500), nullable=True)
    is_system_role = Column(String(10), default='false', nullable=False)  # 'true' or 'false' as string
    created_at = Column(String, nullable=False, default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String, nullable=False, default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())
    created_by = Column(String, ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)
    modified_by = Column(String, ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="tenant_roles")
    user_tenant_roles = relationship("UserTenantRole", back_populates="role", cascade="all, delete-orphan")
    role_permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('tenant_id', 'name', name='uq_tenant_role_tenant_name'),
        Index('idx_tenant_role_tenant_name', 'tenant_id', 'name'),
    )
    
    def __repr__(self):
        return f"<TenantRole(id={self.id}, tenant_id={self.tenant_id}, name={self.name})>"


class UserTenantRole(Base):
    """Association table: User-Role-Tenant relationship."""
    
    __tablename__ = "user_tenant_roles"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    user_id = Column(String, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(String, ForeignKey("tenant_roles.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_at = Column(String, nullable=False, default=lambda: datetime.utcnow().isoformat())
    assigned_by = Column(String, ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)
    
    # Relationships
    user = relationship("Person", foreign_keys=[user_id], back_populates="tenant_memberships", primaryjoin="UserTenantRole.user_id == Person.id")
    tenant = relationship("Tenant", foreign_keys=[tenant_id], back_populates="users")
    role = relationship("TenantRole", back_populates="user_tenant_roles")
    assigned_by_user = relationship("Person", foreign_keys=[assigned_by], viewonly=True, primaryjoin="UserTenantRole.assigned_by == Person.id")
    
    __table_args__ = (
        UniqueConstraint('user_id', 'tenant_id', 'role_id', name='uq_user_tenant_role'),
        Index('idx_user_tenant_role', 'user_id', 'tenant_id', 'role_id'),
    )
    
    def __repr__(self):
        return f"<UserTenantRole(user_id={self.user_id}, tenant_id={self.tenant_id}, role_id={self.role_id})>"


class RolePermission(Base):
    """Association table: TenantRole-Permission relationship."""
    
    __tablename__ = "role_permissions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    role_id = Column(String, ForeignKey("tenant_roles.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id = Column(String, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True)
    granted_at = Column(String, nullable=False, default=lambda: datetime.utcnow().isoformat())
    
    # Relationships
    role = relationship("TenantRole", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")
    
    __table_args__ = (
        UniqueConstraint('role_id', 'permission_id', name='uq_role_permission'),
        Index('idx_role_permission', 'role_id', 'permission_id'),
    )
    
    def __repr__(self):
        return f"<RolePermission(role_id={self.role_id}, permission_id={self.permission_id})>"

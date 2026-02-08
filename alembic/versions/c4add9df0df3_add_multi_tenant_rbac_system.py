"""Add multi-tenant RBAC system

Revision ID: c4add9df0df3
Revises: e83d4d45b357
Create Date: 2026-02-08 20:15:46.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy import String
import uuid
from datetime import datetime


# revision identifiers, used by Alembic.
revision: str = 'c4add9df0df3'
down_revision: Union[str, Sequence[str], None] = 'e83d4d45b357'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add multi-tenant RBAC system."""
    
    # Create parties table (base for Party model)
    op.create_table('parties',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('party_type', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('updated_at', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_parties_id'), 'parties', ['id'], unique=False)
    op.create_index(op.f('ix_parties_party_type'), 'parties', ['party_type'], unique=False)
    
    # Create organizations table (inherits from parties, so no created_at/updated_at here)
    op.create_table('organizations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('company_name', sa.String(length=255), nullable=False),
        sa.Column('tax_id', sa.String(length=50), nullable=True),
        sa.Column('address', sa.JSON(), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.ForeignKeyConstraint(['id'], ['parties.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create persons table (inherits from parties, so no created_at/updated_at here)
    op.create_table('persons',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.Column('password_hash', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.ForeignKeyConstraint(['id'], ['parties.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_persons_email'), 'persons', ['email'], unique=True)
    
    # Create permissions table
    op.create_table('permissions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('resource', sa.String(length=100), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('updated_at', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('resource', 'action', name='uq_permission_resource_action')
    )
    op.create_index(op.f('ix_permissions_id'), 'permissions', ['id'], unique=False)
    op.create_index(op.f('ix_permissions_resource'), 'permissions', ['resource'], unique=False)
    op.create_index(op.f('ix_permissions_action'), 'permissions', ['action'], unique=False)
    op.create_index('idx_permission_resource_action', 'permissions', ['resource', 'action'], unique=False)
    
    # Create tenant_roles table
    op.create_table('tenant_roles',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('is_system_role', sa.String(length=10), nullable=False, server_default='false'),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('updated_at', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_tenant_role_tenant_name')
    )
    op.create_index(op.f('ix_tenant_roles_id'), 'tenant_roles', ['id'], unique=False)
    op.create_index(op.f('ix_tenant_roles_tenant_id'), 'tenant_roles', ['tenant_id'], unique=False)
    op.create_index('idx_tenant_role_tenant_name', 'tenant_roles', ['tenant_id', 'name'], unique=False)
    
    # Create user_tenant_roles table
    op.create_table('user_tenant_roles',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('role_id', sa.String(), nullable=False),
        sa.Column('assigned_at', sa.String(), nullable=False),
        sa.Column('assigned_by', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['persons.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['tenant_roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_by'], ['persons.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'tenant_id', 'role_id', name='uq_user_tenant_role')
    )
    op.create_index(op.f('ix_user_tenant_roles_id'), 'user_tenant_roles', ['id'], unique=False)
    op.create_index(op.f('ix_user_tenant_roles_user_id'), 'user_tenant_roles', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_tenant_roles_tenant_id'), 'user_tenant_roles', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_user_tenant_roles_role_id'), 'user_tenant_roles', ['role_id'], unique=False)
    op.create_index('idx_user_tenant_role', 'user_tenant_roles', ['user_id', 'tenant_id', 'role_id'], unique=False)
    
    # Create role_permissions table
    op.create_table('role_permissions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('role_id', sa.String(), nullable=False),
        sa.Column('permission_id', sa.String(), nullable=False),
        sa.Column('granted_at', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['tenant_roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('role_id', 'permission_id', name='uq_role_permission')
    )
    op.create_index(op.f('ix_role_permissions_id'), 'role_permissions', ['id'], unique=False)
    op.create_index(op.f('ix_role_permissions_role_id'), 'role_permissions', ['role_id'], unique=False)
    op.create_index(op.f('ix_role_permissions_permission_id'), 'role_permissions', ['permission_id'], unique=False)
    op.create_index('idx_role_permission', 'role_permissions', ['role_id', 'permission_id'], unique=False)
    
    # Add organization_id to connections table
    op.add_column('connections', sa.Column('organization_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_connections_organization_id'), 'connections', ['organization_id'], unique=False)
    op.create_foreign_key('fk_connections_organization', 'connections', 'organizations', ['organization_id'], ['id'], ondelete='CASCADE')
    
    # Add organization_id to payroll_risk_analyses table
    op.add_column('payroll_risk_analyses', sa.Column('organization_id', sa.String(), nullable=True))
    op.create_index('idx_payroll_analyses_organization_id', 'payroll_risk_analyses', ['organization_id'], unique=False)
    op.create_foreign_key('fk_payroll_analyses_organization', 'payroll_risk_analyses', 'organizations', ['organization_id'], ['id'], ondelete='CASCADE')
    
    # Add organization_id to mcp_data_cache table
    op.add_column('mcp_data_cache', sa.Column('organization_id', sa.String(), nullable=True))
    op.create_index('idx_mcp_cache_organization_id', 'mcp_data_cache', ['organization_id'], unique=False)
    op.create_foreign_key('fk_mcp_cache_organization', 'mcp_data_cache', 'organizations', ['organization_id'], ['id'], ondelete='CASCADE')
    
    # Insert default data
    now = datetime.utcnow().isoformat()
    
    # Create getGo organization
    # First insert into parties table (parent)
    getgo_id = str(uuid.uuid4())
    op.execute(f"""
        INSERT INTO parties (id, party_type, name, created_at, updated_at)
        VALUES ('{getgo_id}', 'organization', 'getGo', '{now}', '{now}')
    """)
    # Then insert into organizations table (child - no created_at/updated_at, those are in parties)
    op.execute(f"""
        INSERT INTO organizations (id, company_name, is_active)
        VALUES ('{getgo_id}', 'getGo', true)
    """)
    
    # Create permissions
    resources = [
        "connections", "accounts", "invoices", "manual-journals", "bank-transactions",
        "payroll-risk", "cash-strain", "revenue-concentration-risk", "margin-drift",
        "expense-creep", "customer-profitability", "tax-liability", "capital-purchase-timing",
        "dashboard", "favorites"
    ]
    actions = ["view", "create", "edit", "delete", "manage"]
    
    permission_ids = {}
    for resource in resources:
        for action in actions:
            perm_id = str(uuid.uuid4())
            permission_ids[f"{resource}:{action}"] = perm_id
            op.execute(f"""
                INSERT INTO permissions (id, resource, action, description, created_at, updated_at)
                VALUES ('{perm_id}', '{resource}', '{action}', '{resource} {action} permission', '{now}', '{now}')
            """)
    
    # Create default roles for getGo
    admin_role_id = str(uuid.uuid4())
    it_admin_role_id = str(uuid.uuid4())
    accountant_role_id = str(uuid.uuid4())
    controller_role_id = str(uuid.uuid4())
    executive_role_id = str(uuid.uuid4())
    
    op.execute(f"""
        INSERT INTO tenant_roles (id, tenant_id, name, description, is_system_role, created_at, updated_at)
        VALUES 
        ('{admin_role_id}', '{getgo_id}', 'Administrator', 'Full access to all resources', 'true', '{now}', '{now}'),
        ('{it_admin_role_id}', '{getgo_id}', 'IT Administrator', 'Manage connections only', 'true', '{now}', '{now}'),
        ('{accountant_role_id}', '{getgo_id}', 'Accountant', 'Access to accounting resources', 'true', '{now}', '{now}'),
        ('{controller_role_id}', '{getgo_id}', 'Controller', 'Access to payroll risk and cash strain', 'true', '{now}', '{now}'),
        ('{executive_role_id}', '{getgo_id}', 'Finance Executive', 'View-only access to all resources', 'true', '{now}', '{now}')
    """)
    
    # Assign permissions to Administrator (all manage permissions)
    for resource in resources:
        perm_id = permission_ids.get(f"{resource}:manage")
        if perm_id:
            rp_id = str(uuid.uuid4())
            op.execute(f"""
                INSERT INTO role_permissions (id, role_id, permission_id, granted_at)
                VALUES ('{rp_id}', '{admin_role_id}', '{perm_id}', '{now}')
            """)
    
    # Assign permissions to IT Administrator (connections manage)
    perm_id = permission_ids.get("connections:manage")
    if perm_id:
        rp_id = str(uuid.uuid4())
        op.execute(f"""
            INSERT INTO role_permissions (id, role_id, permission_id, granted_at)
            VALUES ('{rp_id}', '{it_admin_role_id}', '{perm_id}', '{now}')
        """)
    
    # Assign permissions to Accountant
    for action in ["view", "create", "edit"]:
        perm_id = permission_ids.get(f"accounts:{action}")
        if perm_id:
            rp_id = str(uuid.uuid4())
            op.execute(f"""
                INSERT INTO role_permissions (id, role_id, permission_id, granted_at)
                VALUES ('{rp_id}', '{accountant_role_id}', '{perm_id}', '{now}')
            """)
    perm_id = permission_ids.get("invoices:view")
    if perm_id:
        rp_id = str(uuid.uuid4())
        op.execute(f"""
            INSERT INTO role_permissions (id, role_id, permission_id, granted_at)
            VALUES ('{rp_id}', '{accountant_role_id}', '{perm_id}', '{now}')
        """)
    for action in ["view", "create", "edit"]:
        perm_id = permission_ids.get(f"manual-journals:{action}")
        if perm_id:
            rp_id = str(uuid.uuid4())
            op.execute(f"""
                INSERT INTO role_permissions (id, role_id, permission_id, granted_at)
                VALUES ('{rp_id}', '{accountant_role_id}', '{perm_id}', '{now}')
            """)
    perm_id = permission_ids.get("bank-transactions:view")
    if perm_id:
        rp_id = str(uuid.uuid4())
        op.execute(f"""
            INSERT INTO role_permissions (id, role_id, permission_id, granted_at)
            VALUES ('{rp_id}', '{accountant_role_id}', '{perm_id}', '{now}')
        """)
    
    # Assign permissions to Controller
    for action in ["view", "create", "edit"]:
        perm_id = permission_ids.get(f"payroll-risk:{action}")
        if perm_id:
            rp_id = str(uuid.uuid4())
            op.execute(f"""
                INSERT INTO role_permissions (id, role_id, permission_id, granted_at)
                VALUES ('{rp_id}', '{controller_role_id}', '{perm_id}', '{now}')
            """)
        perm_id = permission_ids.get(f"cash-strain:{action}")
        if perm_id:
            rp_id = str(uuid.uuid4())
            op.execute(f"""
                INSERT INTO role_permissions (id, role_id, permission_id, granted_at)
                VALUES ('{rp_id}', '{controller_role_id}', '{perm_id}', '{now}')
            """)
    
    # Assign permissions to Finance Executive (all view)
    for resource in resources:
        perm_id = permission_ids.get(f"{resource}:view")
        if perm_id:
            rp_id = str(uuid.uuid4())
            op.execute(f"""
                INSERT INTO role_permissions (id, role_id, permission_id, granted_at)
                VALUES ('{rp_id}', '{executive_role_id}', '{perm_id}', '{now}')
            """)
    
    # Note: Veda Valli user will be created via setup script (scripts/setup_default_data.py)
    # This ensures proper password hashing using the service layer


def downgrade() -> None:
    """Downgrade schema - remove multi-tenant RBAC system."""
    # Remove foreign keys and columns from existing tables
    op.drop_constraint('fk_mcp_cache_organization', 'mcp_data_cache', type_='foreignkey')
    op.drop_index('idx_mcp_cache_organization_id', table_name='mcp_data_cache')
    op.drop_column('mcp_data_cache', 'organization_id')
    
    op.drop_constraint('fk_payroll_analyses_organization', 'payroll_risk_analyses', type_='foreignkey')
    op.drop_index('idx_payroll_analyses_organization_id', table_name='payroll_risk_analyses')
    op.drop_column('payroll_risk_analyses', 'organization_id')
    
    op.drop_constraint('fk_connections_organization', 'connections', type_='foreignkey')
    op.drop_index(op.f('ix_connections_organization_id'), table_name='connections')
    op.drop_column('connections', 'organization_id')
    
    # Drop RBAC tables
    op.drop_table('role_permissions')
    op.drop_table('user_tenant_roles')
    op.drop_table('tenant_roles')
    op.drop_table('permissions')
    op.drop_table('persons')
    op.drop_table('organizations')
    op.drop_table('parties')

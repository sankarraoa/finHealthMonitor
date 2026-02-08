-- Migration script to rename tenant_id to organization_id in RBAC tables
-- This fixes the terminology confusion: "tenant" should only refer to Xero/QuickBooks tenants
-- "organization" refers to customer companies (multi-tenant customers)

-- 1. RENAME COLUMN in tenant_roles table
ALTER TABLE tenant_roles
RENAME COLUMN tenant_id TO organization_id;

-- Update the foreign key constraint name
ALTER TABLE tenant_roles
DROP CONSTRAINT IF EXISTS tenant_roles_tenant_id_fkey;

ALTER TABLE tenant_roles
ADD CONSTRAINT tenant_roles_organization_id_fkey
FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE;

-- Update the unique constraint name
ALTER TABLE tenant_roles
DROP CONSTRAINT IF EXISTS uq_tenant_role_tenant_name;

ALTER TABLE tenant_roles
ADD CONSTRAINT uq_tenant_role_organization_name
UNIQUE (organization_id, name);

-- Update the index name
DROP INDEX IF EXISTS idx_tenant_role_tenant_name;
CREATE INDEX idx_tenant_role_organization_name ON tenant_roles(organization_id, name);

-- 2. RENAME COLUMN in user_tenant_roles table
ALTER TABLE user_tenant_roles
RENAME COLUMN tenant_id TO organization_id;

-- Update the foreign key constraint name
ALTER TABLE user_tenant_roles
DROP CONSTRAINT IF EXISTS user_tenant_roles_tenant_id_fkey;

ALTER TABLE user_tenant_roles
ADD CONSTRAINT user_tenant_roles_organization_id_fkey
FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE;

-- Update the unique constraint name
ALTER TABLE user_tenant_roles
DROP CONSTRAINT IF EXISTS uq_user_tenant_role;

ALTER TABLE user_tenant_roles
ADD CONSTRAINT uq_user_organization_role
UNIQUE (user_id, organization_id, role_id);

-- Update the index name
DROP INDEX IF EXISTS idx_user_tenant_role;
CREATE INDEX idx_user_organization_role ON user_tenant_roles(user_id, organization_id, role_id);

-- Note: The table names (tenant_roles, user_tenant_roles) are kept for backward compatibility
-- Only the column names are changed to reflect the correct terminology

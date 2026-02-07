-- ============================================================================
-- Add organization_id and audit fields (created_by, created_at, modified_by, modified_at)
-- to all tables, and update existing records
-- ============================================================================

-- Constants (replace these values in the queries below)
-- Organization ID: 3afa9332-9a85-4cb6-b858-7bd8e7546bb8
-- Person ID (Veda Valli): 3e3caba8-db08-4ea9-a48c-afc777b5a5c6
-- Current timestamp: 2025-01-27T00:00:00

-- ============================================================================
-- 0. Ensure Organizations and Persons are linked to Parties table
-- ============================================================================
-- First, ensure all organizations have corresponding party records
-- This will only insert if the party record doesn't exist
INSERT INTO parties (id, party_type, name, created_at, updated_at, organization_id, created_by, modified_by)
SELECT 
    o.id,
    'organization' as party_type,
    o.company_name as name,
    '2025-01-27T00:00:00' as created_at,
    '2025-01-27T00:00:00' as updated_at,
    '3afa9332-9a85-4cb6-b858-7bd8e7546bb8' as organization_id,
    '3e3caba8-db08-4ea9-a48c-afc777b5a5c6' as created_by,
    '3e3caba8-db08-4ea9-a48c-afc777b5a5c6' as modified_by
FROM organizations o
WHERE NOT EXISTS (SELECT 1 FROM parties p WHERE p.id = o.id);

-- Ensure all persons have corresponding party records
INSERT INTO parties (id, party_type, name, created_at, updated_at, organization_id, created_by, modified_by)
SELECT 
    p.id,
    'person' as party_type,
    (p.first_name || ' ' || p.last_name) as name,
    '2025-01-27T00:00:00' as created_at,
    '2025-01-27T00:00:00' as updated_at,
    '3afa9332-9a85-4cb6-b858-7bd8e7546bb8' as organization_id,
    '3e3caba8-db08-4ea9-a48c-afc777b5a5c6' as created_by,
    '3e3caba8-db08-4ea9-a48c-afc777b5a5c6' as modified_by
FROM persons p
WHERE NOT EXISTS (SELECT 1 FROM parties pa WHERE pa.id = p.id);

-- ============================================================================
-- 1. PARTIES table
-- ============================================================================
-- Add organization_id (nullable for now, will be set later)
ALTER TABLE parties 
ADD COLUMN IF NOT EXISTS organization_id VARCHAR(255);

-- Add audit fields
ALTER TABLE parties 
ADD COLUMN IF NOT EXISTS created_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS modified_by VARCHAR(255);

-- Note: parties already has created_at and updated_at

-- Add foreign key constraints
ALTER TABLE parties
ADD CONSTRAINT fk_parties_organization_id 
FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE;

ALTER TABLE parties
ADD CONSTRAINT fk_parties_created_by 
FOREIGN KEY (created_by) REFERENCES persons(id) ON DELETE SET NULL;

ALTER TABLE parties
ADD CONSTRAINT fk_parties_modified_by 
FOREIGN KEY (modified_by) REFERENCES persons(id) ON DELETE SET NULL;

-- Update existing records
UPDATE parties 
SET organization_id = '3afa9332-9a85-4cb6-b858-7bd8e7546bb8',
    created_by = '3e3caba8-db08-4ea9-a48c-afc777b5a5c6',
    modified_by = '3e3caba8-db08-4ea9-a48c-afc777b5a5c6'
WHERE organization_id IS NULL OR created_by IS NULL OR modified_by IS NULL;

-- ============================================================================
-- 2. ORGANIZATIONS table
-- ============================================================================
-- Organizations inherit from parties, so they already have the fields from parties
-- But we need to ensure the organization_id points to itself (or parent org)
-- For now, we'll set it to the getGo organization

-- Update existing organizations to reference getGo (or themselves if they are getGo)
UPDATE parties 
SET organization_id = '3afa9332-9a85-4cb6-b858-7bd8e7546bb8'
WHERE id IN (SELECT id FROM organizations)
AND (organization_id IS NULL OR organization_id != id);

-- For getGo organization itself, set organization_id to itself
UPDATE parties 
SET organization_id = id
WHERE id = '3afa9332-9a85-4cb6-b858-7bd8e7546bb8';

-- ============================================================================
-- 3. PERSONS table
-- ============================================================================
-- Persons inherit from parties, so they already have the fields from parties
-- Just update the organization_id for existing persons
UPDATE parties 
SET organization_id = '3afa9332-9a85-4cb6-b858-7bd8e7546bb8'
WHERE id IN (SELECT id FROM persons)
AND organization_id IS NULL;

-- ============================================================================
-- 4. CONNECTIONS table
-- ============================================================================
-- Add audit fields (organization_id, created_at, updated_at already exist)
ALTER TABLE connections 
ADD COLUMN IF NOT EXISTS created_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS modified_by VARCHAR(255);

-- Add foreign key constraints
ALTER TABLE connections
ADD CONSTRAINT fk_connections_created_by 
FOREIGN KEY (created_by) REFERENCES persons(id) ON DELETE SET NULL;

ALTER TABLE connections
ADD CONSTRAINT fk_connections_modified_by 
FOREIGN KEY (modified_by) REFERENCES persons(id) ON DELETE SET NULL;

-- Update existing records
UPDATE connections 
SET organization_id = '3afa9332-9a85-4cb6-b858-7bd8e7546bb8',
    created_by = '3e3caba8-db08-4ea9-a48c-afc777b5a5c6',
    modified_by = '3e3caba8-db08-4ea9-a48c-afc777b5a5c6'
WHERE organization_id IS NULL OR created_by IS NULL OR modified_by IS NULL;

-- ============================================================================
-- 5. TENANTS table
-- ============================================================================
-- Add organization_id and audit fields
ALTER TABLE tenants 
ADD COLUMN IF NOT EXISTS organization_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS created_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS created_at VARCHAR(255),
ADD COLUMN IF NOT EXISTS modified_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS modified_at VARCHAR(255);

-- Add foreign key constraints
ALTER TABLE tenants
ADD CONSTRAINT fk_tenants_organization_id 
FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE;

ALTER TABLE tenants
ADD CONSTRAINT fk_tenants_created_by 
FOREIGN KEY (created_by) REFERENCES persons(id) ON DELETE SET NULL;

ALTER TABLE tenants
ADD CONSTRAINT fk_tenants_modified_by 
FOREIGN KEY (modified_by) REFERENCES persons(id) ON DELETE SET NULL;

-- Update existing records
UPDATE tenants 
SET organization_id = '3afa9332-9a85-4cb6-b858-7bd8e7546bb8',
    created_by = '3e3caba8-db08-4ea9-a48c-afc777b5a5c6',
    created_at = COALESCE(created_at, '2025-01-27T00:00:00'),
    modified_by = '3e3caba8-db08-4ea9-a48c-afc777b5a5c6',
    modified_at = COALESCE(modified_at, '2025-01-27T00:00:00')
WHERE organization_id IS NULL OR created_by IS NULL OR modified_by IS NULL;

-- ============================================================================
-- 6. PAYROLL_RISK_ANALYSES table
-- ============================================================================
-- Add audit fields (organization_id already exists)
ALTER TABLE payroll_risk_analyses 
ADD COLUMN IF NOT EXISTS created_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS created_at VARCHAR(255),
ADD COLUMN IF NOT EXISTS modified_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS modified_at VARCHAR(255);

-- Add foreign key constraints
ALTER TABLE payroll_risk_analyses
ADD CONSTRAINT fk_payroll_risk_analyses_created_by 
FOREIGN KEY (created_by) REFERENCES persons(id) ON DELETE SET NULL;

ALTER TABLE payroll_risk_analyses
ADD CONSTRAINT fk_payroll_risk_analyses_modified_by 
FOREIGN KEY (modified_by) REFERENCES persons(id) ON DELETE SET NULL;

-- Update existing records
UPDATE payroll_risk_analyses 
SET organization_id = '3afa9332-9a85-4cb6-b858-7bd8e7546bb8',
    created_by = '3e3caba8-db08-4ea9-a48c-afc777b5a5c6',
    created_at = COALESCE(created_at, initiated_at),
    modified_by = '3e3caba8-db08-4ea9-a48c-afc777b5a5c6',
    modified_at = COALESCE(modified_at, COALESCE(completed_at, initiated_at))
WHERE organization_id IS NULL OR created_by IS NULL OR modified_by IS NULL;

-- ============================================================================
-- 7. MCP_DATA_CACHE table
-- ============================================================================
-- Add audit fields (organization_id already exists)
ALTER TABLE mcp_data_cache 
ADD COLUMN IF NOT EXISTS created_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS created_at VARCHAR(255),
ADD COLUMN IF NOT EXISTS modified_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS modified_at VARCHAR(255);

-- Add foreign key constraints
ALTER TABLE mcp_data_cache
ADD CONSTRAINT fk_mcp_data_cache_created_by 
FOREIGN KEY (created_by) REFERENCES persons(id) ON DELETE SET NULL;

ALTER TABLE mcp_data_cache
ADD CONSTRAINT fk_mcp_data_cache_modified_by 
FOREIGN KEY (modified_by) REFERENCES persons(id) ON DELETE SET NULL;

-- Update existing records
UPDATE mcp_data_cache 
SET organization_id = '3afa9332-9a85-4cb6-b858-7bd8e7546bb8',
    created_by = '3e3caba8-db08-4ea9-a48c-afc777b5a5c6',
    created_at = COALESCE(created_at, cached_at),
    modified_by = '3e3caba8-db08-4ea9-a48c-afc777b5a5c6',
    modified_at = COALESCE(modified_at, cached_at)
WHERE organization_id IS NULL OR created_by IS NULL OR modified_by IS NULL;

-- ============================================================================
-- 8. PERMISSIONS table
-- ============================================================================
-- Add organization_id and audit fields (created_at, updated_at already exist)
ALTER TABLE permissions 
ADD COLUMN IF NOT EXISTS organization_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS created_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS modified_by VARCHAR(255);

-- Add foreign key constraints
ALTER TABLE permissions
ADD CONSTRAINT fk_permissions_organization_id 
FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE;

ALTER TABLE permissions
ADD CONSTRAINT fk_permissions_created_by 
FOREIGN KEY (created_by) REFERENCES persons(id) ON DELETE SET NULL;

ALTER TABLE permissions
ADD CONSTRAINT fk_permissions_modified_by 
FOREIGN KEY (modified_by) REFERENCES persons(id) ON DELETE SET NULL;

-- Update existing records
UPDATE permissions 
SET organization_id = '3afa9332-9a85-4cb6-b858-7bd8e7546bb8',
    created_by = '3e3caba8-db08-4ea9-a48c-afc777b5a5c6',
    modified_by = '3e3caba8-db08-4ea9-a48c-afc777b5a5c6'
WHERE organization_id IS NULL OR created_by IS NULL OR modified_by IS NULL;

-- ============================================================================
-- 9. TENANT_ROLES table
-- ============================================================================
-- Add audit fields (tenant_id is organization_id, created_at, updated_at already exist)
ALTER TABLE tenant_roles 
ADD COLUMN IF NOT EXISTS created_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS modified_by VARCHAR(255);

-- Add foreign key constraints
ALTER TABLE tenant_roles
ADD CONSTRAINT fk_tenant_roles_created_by 
FOREIGN KEY (created_by) REFERENCES persons(id) ON DELETE SET NULL;

ALTER TABLE tenant_roles
ADD CONSTRAINT fk_tenant_roles_modified_by 
FOREIGN KEY (modified_by) REFERENCES persons(id) ON DELETE SET NULL;

-- Update existing records
UPDATE tenant_roles 
SET created_by = '3e3caba8-db08-4ea9-a48c-afc777b5a5c6',
    modified_by = '3e3caba8-db08-4ea9-a48c-afc777b5a5c6'
WHERE created_by IS NULL OR modified_by IS NULL;

-- ============================================================================
-- 10. USER_TENANT_ROLES table
-- ============================================================================
-- Add organization_id and audit fields (assigned_at exists, but we need created_at/modified_at)
ALTER TABLE user_tenant_roles 
ADD COLUMN IF NOT EXISTS organization_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS created_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS created_at VARCHAR(255),
ADD COLUMN IF NOT EXISTS modified_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS modified_at VARCHAR(255);

-- Add foreign key constraints
ALTER TABLE user_tenant_roles
ADD CONSTRAINT fk_user_tenant_roles_organization_id 
FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE;

ALTER TABLE user_tenant_roles
ADD CONSTRAINT fk_user_tenant_roles_created_by 
FOREIGN KEY (created_by) REFERENCES persons(id) ON DELETE SET NULL;

ALTER TABLE user_tenant_roles
ADD CONSTRAINT fk_user_tenant_roles_modified_by 
FOREIGN KEY (modified_by) REFERENCES persons(id) ON DELETE SET NULL;

-- Update existing records (organization_id should match tenant_id)
UPDATE user_tenant_roles 
SET organization_id = tenant_id,
    created_by = COALESCE(assigned_by, '3e3caba8-db08-4ea9-a48c-afc777b5a5c6'),
    created_at = COALESCE(created_at, assigned_at),
    modified_by = COALESCE(assigned_by, '3e3caba8-db08-4ea9-a48c-afc777b5a5c6'),
    modified_at = COALESCE(modified_at, assigned_at)
WHERE organization_id IS NULL OR created_by IS NULL OR modified_by IS NULL;

-- ============================================================================
-- 11. ROLE_PERMISSIONS table
-- ============================================================================
-- Add organization_id and audit fields (granted_at exists, but we need created_at/modified_at)
ALTER TABLE role_permissions 
ADD COLUMN IF NOT EXISTS organization_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS created_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS created_at VARCHAR(255),
ADD COLUMN IF NOT EXISTS modified_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS modified_at VARCHAR(255);

-- Add foreign key constraints
ALTER TABLE role_permissions
ADD CONSTRAINT fk_role_permissions_organization_id 
FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE;

ALTER TABLE role_permissions
ADD CONSTRAINT fk_role_permissions_created_by 
FOREIGN KEY (created_by) REFERENCES persons(id) ON DELETE SET NULL;

ALTER TABLE role_permissions
ADD CONSTRAINT fk_role_permissions_modified_by 
FOREIGN KEY (modified_by) REFERENCES persons(id) ON DELETE SET NULL;

-- Update existing records (organization_id from tenant_roles)
UPDATE role_permissions 
SET organization_id = (
    SELECT tenant_id FROM tenant_roles WHERE tenant_roles.id = role_permissions.role_id
),
    created_by = '3e3caba8-db08-4ea9-a48c-afc777b5a5c6',
    created_at = COALESCE(created_at, granted_at),
    modified_by = '3e3caba8-db08-4ea9-a48c-afc777b5a5c6',
    modified_at = COALESCE(modified_at, granted_at)
WHERE organization_id IS NULL OR created_by IS NULL OR modified_by IS NULL;

-- ============================================================================
-- Create indexes for performance
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_parties_organization_id ON parties(organization_id);
CREATE INDEX IF NOT EXISTS idx_parties_created_by ON parties(created_by);
CREATE INDEX IF NOT EXISTS idx_parties_modified_by ON parties(modified_by);

CREATE INDEX IF NOT EXISTS idx_connections_created_by ON connections(created_by);
CREATE INDEX IF NOT EXISTS idx_connections_modified_by ON connections(modified_by);

CREATE INDEX IF NOT EXISTS idx_tenants_organization_id ON tenants(organization_id);
CREATE INDEX IF NOT EXISTS idx_tenants_created_by ON tenants(created_by);
CREATE INDEX IF NOT EXISTS idx_tenants_modified_by ON tenants(modified_by);

CREATE INDEX IF NOT EXISTS idx_payroll_risk_analyses_created_by ON payroll_risk_analyses(created_by);
CREATE INDEX IF NOT EXISTS idx_payroll_risk_analyses_modified_by ON payroll_risk_analyses(modified_by);

CREATE INDEX IF NOT EXISTS idx_mcp_data_cache_created_by ON mcp_data_cache(created_by);
CREATE INDEX IF NOT EXISTS idx_mcp_data_cache_modified_by ON mcp_data_cache(modified_by);

CREATE INDEX IF NOT EXISTS idx_permissions_organization_id ON permissions(organization_id);
CREATE INDEX IF NOT EXISTS idx_permissions_created_by ON permissions(created_by);
CREATE INDEX IF NOT EXISTS idx_permissions_modified_by ON permissions(modified_by);

CREATE INDEX IF NOT EXISTS idx_tenant_roles_created_by ON tenant_roles(created_by);
CREATE INDEX IF NOT EXISTS idx_tenant_roles_modified_by ON tenant_roles(modified_by);

CREATE INDEX IF NOT EXISTS idx_user_tenant_roles_organization_id ON user_tenant_roles(organization_id);
CREATE INDEX IF NOT EXISTS idx_user_tenant_roles_created_by ON user_tenant_roles(created_by);
CREATE INDEX IF NOT EXISTS idx_user_tenant_roles_modified_by ON user_tenant_roles(modified_by);

CREATE INDEX IF NOT EXISTS idx_role_permissions_organization_id ON role_permissions(organization_id);
CREATE INDEX IF NOT EXISTS idx_role_permissions_created_by ON role_permissions(created_by);
CREATE INDEX IF NOT EXISTS idx_role_permissions_modified_by ON role_permissions(modified_by);

-- ============================================================================
-- Verification queries (run these to check the results)
-- ============================================================================

-- Check that all tables have organization_id set
SELECT 'parties' as table_name, COUNT(*) as total, COUNT(organization_id) as with_org_id 
FROM parties
UNION ALL
SELECT 'organizations', COUNT(*), COUNT(organization_id) FROM organizations
UNION ALL
SELECT 'persons', COUNT(*), COUNT(organization_id) FROM persons
UNION ALL
SELECT 'connections', COUNT(*), COUNT(organization_id) FROM connections
UNION ALL
SELECT 'tenants', COUNT(*), COUNT(organization_id) FROM tenants
UNION ALL
SELECT 'payroll_risk_analyses', COUNT(*), COUNT(organization_id) FROM payroll_risk_analyses
UNION ALL
SELECT 'mcp_data_cache', COUNT(*), COUNT(organization_id) FROM mcp_data_cache
UNION ALL
SELECT 'permissions', COUNT(*), COUNT(organization_id) FROM permissions
UNION ALL
SELECT 'user_tenant_roles', COUNT(*), COUNT(organization_id) FROM user_tenant_roles
UNION ALL
SELECT 'role_permissions', COUNT(*), COUNT(organization_id) FROM role_permissions;

-- Check that all tables have audit fields set
SELECT 'parties' as table_name, 
    COUNT(*) as total, 
    COUNT(created_by) as with_created_by,
    COUNT(modified_by) as with_modified_by
FROM parties
UNION ALL
SELECT 'connections', COUNT(*), COUNT(created_by), COUNT(modified_by) FROM connections
UNION ALL
SELECT 'tenants', COUNT(*), COUNT(created_by), COUNT(modified_by) FROM tenants
UNION ALL
SELECT 'payroll_risk_analyses', COUNT(*), COUNT(created_by), COUNT(modified_by) FROM payroll_risk_analyses
UNION ALL
SELECT 'mcp_data_cache', COUNT(*), COUNT(created_by), COUNT(modified_by) FROM mcp_data_cache
UNION ALL
SELECT 'permissions', COUNT(*), COUNT(created_by), COUNT(modified_by) FROM permissions
UNION ALL
SELECT 'tenant_roles', COUNT(*), COUNT(created_by), COUNT(modified_by) FROM tenant_roles
UNION ALL
SELECT 'user_tenant_roles', COUNT(*), COUNT(created_by), COUNT(modified_by) FROM user_tenant_roles
UNION ALL
SELECT 'role_permissions', COUNT(*), COUNT(created_by), COUNT(modified_by) FROM role_permissions;

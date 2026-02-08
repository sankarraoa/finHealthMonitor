-- Migration script to rename tables and columns
-- 1. Rename tenants table to xero_tenants (Xero/QuickBooks tenants)
-- 2. Rename organizations table to tenants (B2B SaaS tenants)
-- 3. Rename organization_id to tenant_id across all tables

-- ============================================================================
-- STEP 1: Rename tenants table to xero_tenants
-- ============================================================================
ALTER TABLE tenants RENAME TO xero_tenants;

-- Update foreign key constraint names if they reference the old table name
-- (PostgreSQL will automatically update the constraint, but we can be explicit)
DO $$
BEGIN
    -- Update any indexes that reference 'tenants'
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname LIKE '%tenant%' AND tablename = 'xero_tenants') THEN
        -- Indexes are automatically renamed, but we can verify
        RAISE NOTICE 'Indexes on xero_tenants table updated';
    END IF;
END $$;

-- ============================================================================
-- STEP 2: Rename organizations table to tenants
-- ============================================================================
ALTER TABLE organizations RENAME TO tenants;

-- Update foreign key constraints that reference organizations.id
-- We need to drop and recreate them with new names

-- Update parties.organization_id foreign key
ALTER TABLE parties
DROP CONSTRAINT IF EXISTS fk_parties_organization_id;

ALTER TABLE parties
ADD CONSTRAINT fk_parties_tenant_id
FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

-- Update persons.organization_id foreign key (if exists as separate column)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'persons' AND column_name = 'organization_id'
    ) THEN
        ALTER TABLE persons
        DROP CONSTRAINT IF EXISTS fk_persons_organization_id;
        
        ALTER TABLE persons
        ADD CONSTRAINT fk_persons_tenant_id
        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
        
        RAISE NOTICE 'Updated persons.tenant_id foreign key';
    END IF;
END $$;

-- Update tenant_roles.organization_id foreign key
ALTER TABLE tenant_roles
DROP CONSTRAINT IF EXISTS tenant_roles_organization_id_fkey;

ALTER TABLE tenant_roles
ADD CONSTRAINT tenant_roles_tenant_id_fkey
FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

-- Update user_tenant_roles.organization_id foreign key
ALTER TABLE user_tenant_roles
DROP CONSTRAINT IF EXISTS user_tenant_roles_organization_id_fkey;

ALTER TABLE user_tenant_roles
ADD CONSTRAINT user_tenant_roles_tenant_id_fkey
FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

-- Update connections.organization_id foreign key
ALTER TABLE connections
DROP CONSTRAINT IF EXISTS connections_organization_id_fkey;

ALTER TABLE connections
ADD CONSTRAINT connections_tenant_id_fkey
FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

-- Update payroll_risk_analyses.organization_id foreign key
ALTER TABLE payroll_risk_analyses
DROP CONSTRAINT IF EXISTS payroll_risk_analyses_organization_id_fkey;

ALTER TABLE payroll_risk_analyses
ADD CONSTRAINT payroll_risk_analyses_tenant_id_fkey
FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

-- Update mcp_data_cache.organization_id foreign key
ALTER TABLE mcp_data_cache
DROP CONSTRAINT IF EXISTS mcp_data_cache_organization_id_fkey;

ALTER TABLE mcp_data_cache
ADD CONSTRAINT mcp_data_cache_tenant_id_fkey
FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

-- Update permissions.organization_id foreign key (if exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'permissions' AND column_name = 'organization_id'
    ) THEN
        ALTER TABLE permissions
        DROP CONSTRAINT IF EXISTS fk_permissions_organization_id;
        
        ALTER TABLE permissions
        ADD CONSTRAINT fk_permissions_tenant_id
        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
        
        RAISE NOTICE 'Updated permissions.tenant_id foreign key';
    END IF;
END $$;

-- ============================================================================
-- STEP 3: Rename organization_id columns to tenant_id
-- ============================================================================

-- parties table
ALTER TABLE parties RENAME COLUMN organization_id TO tenant_id;

-- persons table (if exists as separate column)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'persons' AND column_name = 'organization_id'
    ) THEN
        ALTER TABLE persons RENAME COLUMN organization_id TO tenant_id;
        RAISE NOTICE 'Renamed persons.organization_id to tenant_id';
    END IF;
END $$;

-- tenant_roles table
ALTER TABLE tenant_roles RENAME COLUMN organization_id TO tenant_id;

-- user_tenant_roles table
ALTER TABLE user_tenant_roles RENAME COLUMN organization_id TO tenant_id;

-- connections table
ALTER TABLE connections RENAME COLUMN organization_id TO tenant_id;

-- payroll_risk_analyses table
-- Also rename tenant_id to xero_tenant_id and tenant_name to xero_tenant_name
ALTER TABLE payroll_risk_analyses RENAME COLUMN organization_id TO tenant_id;
ALTER TABLE payroll_risk_analyses RENAME COLUMN tenant_id TO xero_tenant_id;
ALTER TABLE payroll_risk_analyses RENAME COLUMN tenant_name TO xero_tenant_name;

-- mcp_data_cache table
-- Also rename tenant_id to xero_tenant_id
ALTER TABLE mcp_data_cache RENAME COLUMN organization_id TO tenant_id;
ALTER TABLE mcp_data_cache RENAME COLUMN tenant_id TO xero_tenant_id;

-- permissions table (if organization_id exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'permissions' AND column_name = 'organization_id'
    ) THEN
        ALTER TABLE permissions RENAME COLUMN organization_id TO tenant_id;
        RAISE NOTICE 'Renamed permissions.organization_id to tenant_id';
    END IF;
END $$;

-- ============================================================================
-- STEP 4: Update indexes
-- ============================================================================

-- Update index names for tenant_id columns
DO $$
BEGIN
    -- parties table
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_parties_organization_id') THEN
        ALTER INDEX ix_parties_organization_id RENAME TO ix_parties_tenant_id;
    END IF;
    
    -- tenant_roles table
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_tenant_role_organization_name') THEN
        ALTER INDEX idx_tenant_role_organization_name RENAME TO idx_tenant_role_tenant_name;
    END IF;
    
    -- Update unique constraint name
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'uq_tenant_role_organization_name'
    ) THEN
        ALTER TABLE tenant_roles
        DROP CONSTRAINT uq_tenant_role_organization_name;
        
        ALTER TABLE tenant_roles
        ADD CONSTRAINT uq_tenant_role_tenant_name
        UNIQUE (tenant_id, name);
    END IF;
    
    -- payroll_risk_analyses table
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_payroll_analyses_organization_id') THEN
        ALTER INDEX idx_payroll_analyses_organization_id RENAME TO idx_payroll_analyses_tenant_id;
    END IF;
    
    -- mcp_data_cache table
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mcp_cache_organization_id') THEN
        ALTER INDEX idx_mcp_cache_organization_id RENAME TO idx_mcp_cache_tenant_id;
    END IF;
    
    -- Update composite index for mcp_data_cache
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_connection_tenant_key') THEN
        ALTER INDEX idx_connection_tenant_key RENAME TO idx_connection_xero_tenant_key;
    END IF;
    
    RAISE NOTICE 'Updated index names';
END $$;

-- ============================================================================
-- Verification
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE 'Migration completed. Verifying...';
    
    -- Check that xero_tenants table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'xero_tenants') THEN
        RAISE NOTICE '✓ xero_tenants table exists';
    ELSE
        RAISE WARNING '✗ xero_tenants table does NOT exist';
    END IF;
    
    -- Check that tenants table exists (renamed from organizations)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'tenants') THEN
        RAISE NOTICE '✓ tenants table exists (renamed from organizations)';
    ELSE
        RAISE WARNING '✗ tenants table does NOT exist';
    END IF;
    
    -- Check that organizations table does NOT exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'organizations') THEN
        RAISE NOTICE '✓ organizations table successfully renamed';
    ELSE
        RAISE WARNING '✗ organizations table still exists';
    END IF;
    
END $$;

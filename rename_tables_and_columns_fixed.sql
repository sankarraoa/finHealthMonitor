-- Fixed migration script to rename tables and columns
-- Order: 1) Rename columns first, 2) Then update foreign keys

-- ============================================================================
-- STEP 1: Rename tenants table to xero_tenants (Xero/QuickBooks tenants)
-- ============================================================================
ALTER TABLE tenants RENAME TO xero_tenants;

-- ============================================================================
-- STEP 2: Rename organizations table to tenants (B2B SaaS tenants)
-- ============================================================================
ALTER TABLE organizations RENAME TO tenants;

-- ============================================================================
-- STEP 3: Rename organization_id columns to tenant_id
-- IMPORTANT: Do this BEFORE updating foreign keys
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
-- IMPORTANT: This table already has tenant_id (Xero tenant), so we need to:
-- 1. First rename existing tenant_id to xero_tenant_id
-- 2. Then rename organization_id to tenant_id
-- 3. Rename tenant_name to xero_tenant_name
DO $$
BEGIN
    -- Check if organization_id exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'payroll_risk_analyses' AND column_name = 'organization_id'
    ) THEN
        -- First rename existing tenant_id to xero_tenant_id (if it exists)
        IF EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'payroll_risk_analyses' AND column_name = 'tenant_id'
        ) THEN
            ALTER TABLE payroll_risk_analyses RENAME COLUMN tenant_id TO xero_tenant_id;
            RAISE NOTICE 'Renamed payroll_risk_analyses.tenant_id to xero_tenant_id';
        END IF;
        
        -- Rename tenant_name to xero_tenant_name (if it exists)
        IF EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'payroll_risk_analyses' AND column_name = 'tenant_name'
        ) THEN
            ALTER TABLE payroll_risk_analyses RENAME COLUMN tenant_name TO xero_tenant_name;
            RAISE NOTICE 'Renamed payroll_risk_analyses.tenant_name to xero_tenant_name';
        END IF;
        
        -- Now rename organization_id to tenant_id
        ALTER TABLE payroll_risk_analyses RENAME COLUMN organization_id TO tenant_id;
        RAISE NOTICE 'Renamed payroll_risk_analyses.organization_id to tenant_id';
    END IF;
END $$;

-- mcp_data_cache table
-- IMPORTANT: This table already has tenant_id (Xero tenant), so we need to:
-- 1. First rename existing tenant_id to xero_tenant_id
-- 2. Then rename organization_id to tenant_id
DO $$
BEGIN
    -- Check if organization_id exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'mcp_data_cache' AND column_name = 'organization_id'
    ) THEN
        -- First rename existing tenant_id to xero_tenant_id (if it exists)
        IF EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'mcp_data_cache' AND column_name = 'tenant_id'
        ) THEN
            ALTER TABLE mcp_data_cache RENAME COLUMN tenant_id TO xero_tenant_id;
            RAISE NOTICE 'Renamed mcp_data_cache.tenant_id to xero_tenant_id';
        END IF;
        
        -- Now rename organization_id to tenant_id
        ALTER TABLE mcp_data_cache RENAME COLUMN organization_id TO tenant_id;
        RAISE NOTICE 'Renamed mcp_data_cache.organization_id to tenant_id';
    END IF;
END $$;

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
-- STEP 4: Update foreign key constraints (now that columns are renamed)
-- ============================================================================

-- Update parties.tenant_id foreign key
ALTER TABLE parties
DROP CONSTRAINT IF EXISTS fk_parties_organization_id;

ALTER TABLE parties
DROP CONSTRAINT IF EXISTS fk_parties_tenant_id;

ALTER TABLE parties
ADD CONSTRAINT fk_parties_tenant_id
FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

-- Update persons.tenant_id foreign key (if exists as separate column)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'persons' AND column_name = 'tenant_id'
    ) THEN
        ALTER TABLE persons
        DROP CONSTRAINT IF EXISTS fk_persons_organization_id;
        
        ALTER TABLE persons
        DROP CONSTRAINT IF EXISTS fk_persons_tenant_id;
        
        ALTER TABLE persons
        ADD CONSTRAINT fk_persons_tenant_id
        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
        
        RAISE NOTICE 'Updated persons.tenant_id foreign key';
    END IF;
END $$;

-- Update tenant_roles.tenant_id foreign key
ALTER TABLE tenant_roles
DROP CONSTRAINT IF EXISTS tenant_roles_organization_id_fkey;

ALTER TABLE tenant_roles
DROP CONSTRAINT IF EXISTS tenant_roles_tenant_id_fkey;

ALTER TABLE tenant_roles
ADD CONSTRAINT tenant_roles_tenant_id_fkey
FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

-- Update user_tenant_roles.tenant_id foreign key
ALTER TABLE user_tenant_roles
DROP CONSTRAINT IF EXISTS user_tenant_roles_organization_id_fkey;

ALTER TABLE user_tenant_roles
DROP CONSTRAINT IF EXISTS user_tenant_roles_tenant_id_fkey;

ALTER TABLE user_tenant_roles
ADD CONSTRAINT user_tenant_roles_tenant_id_fkey
FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

-- Update connections.tenant_id foreign key
ALTER TABLE connections
DROP CONSTRAINT IF EXISTS connections_organization_id_fkey;

ALTER TABLE connections
DROP CONSTRAINT IF EXISTS connections_tenant_id_fkey;

ALTER TABLE connections
ADD CONSTRAINT connections_tenant_id_fkey
FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;

-- Update payroll_risk_analyses.tenant_id foreign key
-- Note: We may need to clean up invalid data first
DO $$
BEGIN
    -- First, set tenant_id to NULL for records that don't have valid tenant references
    -- (These might be old Xero tenant IDs that were mistakenly in organization_id)
    UPDATE payroll_risk_analyses
    SET tenant_id = NULL
    WHERE tenant_id IS NOT NULL 
      AND tenant_id NOT IN (SELECT id FROM tenants);
    
    RAISE NOTICE 'Cleaned up invalid tenant_id values in payroll_risk_analyses';
    
    -- Now add the foreign key constraint
    ALTER TABLE payroll_risk_analyses
    DROP CONSTRAINT IF EXISTS payroll_risk_analyses_organization_id_fkey;
    
    ALTER TABLE payroll_risk_analyses
    DROP CONSTRAINT IF EXISTS payroll_risk_analyses_tenant_id_fkey;
    
    ALTER TABLE payroll_risk_analyses
    ADD CONSTRAINT payroll_risk_analyses_tenant_id_fkey
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
    
    RAISE NOTICE 'Updated payroll_risk_analyses.tenant_id foreign key';
END $$;

-- Update mcp_data_cache.tenant_id foreign key
-- Note: We may need to clean up invalid data first
DO $$
BEGIN
    -- First, set tenant_id to NULL for records that don't have valid tenant references
    UPDATE mcp_data_cache
    SET tenant_id = NULL
    WHERE tenant_id IS NOT NULL 
      AND tenant_id NOT IN (SELECT id FROM tenants);
    
    RAISE NOTICE 'Cleaned up invalid tenant_id values in mcp_data_cache';
    
    -- Now add the foreign key constraint
    ALTER TABLE mcp_data_cache
    DROP CONSTRAINT IF EXISTS mcp_data_cache_organization_id_fkey;
    
    ALTER TABLE mcp_data_cache
    DROP CONSTRAINT IF EXISTS mcp_data_cache_tenant_id_fkey;
    
    ALTER TABLE mcp_data_cache
    ADD CONSTRAINT mcp_data_cache_tenant_id_fkey
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
    
    RAISE NOTICE 'Updated mcp_data_cache.tenant_id foreign key';
END $$;

-- Update permissions.tenant_id foreign key (if exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'permissions' AND column_name = 'tenant_id'
    ) THEN
        ALTER TABLE permissions
        DROP CONSTRAINT IF EXISTS fk_permissions_organization_id;
        
        ALTER TABLE permissions
        DROP CONSTRAINT IF EXISTS fk_permissions_tenant_id;
        
        ALTER TABLE permissions
        ADD CONSTRAINT fk_permissions_tenant_id
        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
        
        RAISE NOTICE 'Updated permissions.tenant_id foreign key';
    END IF;
END $$;

-- ============================================================================
-- STEP 5: Update indexes and constraints
-- ============================================================================

DO $$
BEGIN
    -- Update index names for tenant_id columns
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_parties_organization_id') THEN
        ALTER INDEX ix_parties_organization_id RENAME TO ix_parties_tenant_id;
    END IF;
    
    -- tenant_roles table - update unique constraint and index
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
    
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_tenant_role_organization_name') THEN
        ALTER INDEX idx_tenant_role_organization_name RENAME TO idx_tenant_role_tenant_name;
    END IF;
    
    -- payroll_risk_analyses table
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_payroll_analyses_organization_id') THEN
        ALTER INDEX idx_payroll_analyses_organization_id RENAME TO idx_payroll_analyses_tenant_id;
    END IF;
    
    -- mcp_data_cache table
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mcp_cache_organization_id') THEN
        ALTER INDEX idx_mcp_cache_organization_id RENAME TO idx_mcp_cache_tenant_id;
    END IF;
    
    -- Update composite index for mcp_data_cache (rename tenant_id to xero_tenant_id in index)
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_connection_tenant_key') THEN
        DROP INDEX idx_connection_tenant_key;
        CREATE INDEX idx_connection_xero_tenant_key ON mcp_data_cache(connection_id, xero_tenant_id, cache_key);
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

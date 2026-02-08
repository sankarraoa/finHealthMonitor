-- Safe migration script to rename tenant_id to organization_id in RBAC tables
-- This script checks if columns exist before renaming to avoid errors

-- 1. Handle tenant_roles table
DO $$
BEGIN
    -- Check if tenant_id exists and organization_id doesn't exist
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'tenant_roles' AND column_name = 'tenant_id'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'tenant_roles' AND column_name = 'organization_id'
    ) THEN
        -- Rename the column
        ALTER TABLE tenant_roles RENAME COLUMN tenant_id TO organization_id;
        RAISE NOTICE 'Renamed tenant_id to organization_id in tenant_roles';
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'tenant_roles' AND column_name = 'organization_id'
    ) THEN
        RAISE NOTICE 'organization_id already exists in tenant_roles, skipping rename';
    ELSE
        RAISE NOTICE 'tenant_id does not exist in tenant_roles';
    END IF;
END $$;

-- Update foreign key constraint for tenant_roles if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'tenant_roles_tenant_id_fkey'
    ) THEN
        ALTER TABLE tenant_roles DROP CONSTRAINT tenant_roles_tenant_id_fkey;
        ALTER TABLE tenant_roles 
        ADD CONSTRAINT tenant_roles_organization_id_fkey
        FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE;
        RAISE NOTICE 'Updated foreign key constraint for tenant_roles';
    END IF;
END $$;

-- Update unique constraint for tenant_roles if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'uq_tenant_role_tenant_name'
    ) THEN
        ALTER TABLE tenant_roles DROP CONSTRAINT uq_tenant_role_tenant_name;
        ALTER TABLE tenant_roles 
        ADD CONSTRAINT uq_tenant_role_organization_name
        UNIQUE (organization_id, name);
        RAISE NOTICE 'Updated unique constraint for tenant_roles';
    END IF;
END $$;

-- Update index for tenant_roles if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE indexname = 'idx_tenant_role_tenant_name'
    ) THEN
        DROP INDEX IF EXISTS idx_tenant_role_tenant_name;
        CREATE INDEX idx_tenant_role_organization_name ON tenant_roles(organization_id, name);
        RAISE NOTICE 'Updated index for tenant_roles';
    END IF;
END $$;

-- 2. Handle user_tenant_roles table
DO $$
BEGIN
    -- Check if tenant_id exists and organization_id doesn't exist
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_tenant_roles' AND column_name = 'tenant_id'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_tenant_roles' AND column_name = 'organization_id'
    ) THEN
        -- Rename the column
        ALTER TABLE user_tenant_roles RENAME COLUMN tenant_id TO organization_id;
        RAISE NOTICE 'Renamed tenant_id to organization_id in user_tenant_roles';
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_tenant_roles' AND column_name = 'organization_id'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_tenant_roles' AND column_name = 'tenant_id'
    ) THEN
        -- Both columns exist - need to migrate data and drop tenant_id
        RAISE NOTICE 'Both tenant_id and organization_id exist in user_tenant_roles';
        RAISE NOTICE 'Copying data from tenant_id to organization_id where organization_id is NULL';
        UPDATE user_tenant_roles 
        SET organization_id = tenant_id 
        WHERE organization_id IS NULL AND tenant_id IS NOT NULL;
        
        RAISE NOTICE 'Dropping tenant_id column';
        ALTER TABLE user_tenant_roles DROP COLUMN tenant_id;
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_tenant_roles' AND column_name = 'organization_id'
    ) THEN
        RAISE NOTICE 'organization_id already exists in user_tenant_roles, tenant_id does not exist';
    ELSE
        RAISE NOTICE 'tenant_id does not exist in user_tenant_roles';
    END IF;
END $$;

-- Update foreign key constraint for user_tenant_roles if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'user_tenant_roles_tenant_id_fkey'
    ) THEN
        ALTER TABLE user_tenant_roles DROP CONSTRAINT user_tenant_roles_tenant_id_fkey;
        ALTER TABLE user_tenant_roles 
        ADD CONSTRAINT user_tenant_roles_organization_id_fkey
        FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE;
        RAISE NOTICE 'Updated foreign key constraint for user_tenant_roles';
    END IF;
END $$;

-- Update unique constraint for user_tenant_roles if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'uq_user_tenant_role'
    ) THEN
        ALTER TABLE user_tenant_roles DROP CONSTRAINT uq_user_tenant_role;
        ALTER TABLE user_tenant_roles 
        ADD CONSTRAINT uq_user_organization_role
        UNIQUE (user_id, organization_id, role_id);
        RAISE NOTICE 'Updated unique constraint for user_tenant_roles';
    END IF;
END $$;

-- Update index for user_tenant_roles if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE indexname = 'idx_user_tenant_role'
    ) THEN
        DROP INDEX IF EXISTS idx_user_tenant_role;
        CREATE INDEX idx_user_organization_role ON user_tenant_roles(user_id, organization_id, role_id);
        RAISE NOTICE 'Updated index for user_tenant_roles';
    END IF;
END $$;

-- Final verification
DO $$
BEGIN
    RAISE NOTICE 'Migration completed. Verifying final state...';
    
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'tenant_roles' AND column_name = 'organization_id'
    ) THEN
        RAISE NOTICE '✓ tenant_roles has organization_id column';
    ELSE
        RAISE WARNING '✗ tenant_roles does NOT have organization_id column';
    END IF;
    
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_tenant_roles' AND column_name = 'organization_id'
    ) THEN
        RAISE NOTICE '✓ user_tenant_roles has organization_id column';
    ELSE
        RAISE WARNING '✗ user_tenant_roles does NOT have organization_id column';
    END IF;
    
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'tenant_roles' AND column_name = 'tenant_id'
    ) THEN
        RAISE WARNING '✗ tenant_roles still has tenant_id column (should be removed)';
    END IF;
    
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_tenant_roles' AND column_name = 'tenant_id'
    ) THEN
        RAISE WARNING '✗ user_tenant_roles still has tenant_id column (should be removed)';
    END IF;
END $$;

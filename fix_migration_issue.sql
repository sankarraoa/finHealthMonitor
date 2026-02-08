-- Fix migration issue: user_tenant_roles already has organization_id
-- This script handles the case where organization_id already exists

-- First, check if both tenant_id and organization_id exist in user_tenant_roles
-- If so, we need to:
-- 1. Copy data from tenant_id to organization_id where organization_id is NULL
-- 2. Drop the tenant_id column

DO $$
BEGIN
    -- Check if both columns exist
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_tenant_roles' AND column_name = 'tenant_id'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_tenant_roles' AND column_name = 'organization_id'
    ) THEN
        RAISE NOTICE 'Both tenant_id and organization_id exist. Migrating data...';
        
        -- Copy data from tenant_id to organization_id where organization_id is NULL
        UPDATE user_tenant_roles 
        SET organization_id = tenant_id 
        WHERE organization_id IS NULL AND tenant_id IS NOT NULL;
        
        RAISE NOTICE 'Data migrated. Dropping tenant_id column...';
        
        -- Drop the tenant_id column
        ALTER TABLE user_tenant_roles DROP COLUMN tenant_id;
        
        RAISE NOTICE 'tenant_id column dropped successfully';
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_tenant_roles' AND column_name = 'tenant_id'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_tenant_roles' AND column_name = 'organization_id'
    ) THEN
        -- Only tenant_id exists, rename it
        RAISE NOTICE 'Only tenant_id exists. Renaming to organization_id...';
        ALTER TABLE user_tenant_roles RENAME COLUMN tenant_id TO organization_id;
        RAISE NOTICE 'Renamed successfully';
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_tenant_roles' AND column_name = 'organization_id'
    ) THEN
        RAISE NOTICE 'organization_id already exists. Checking if tenant_id needs to be dropped...';
        
        -- If tenant_id still exists, drop it
        IF EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'user_tenant_roles' AND column_name = 'tenant_id'
        ) THEN
            -- Copy any remaining data first
            UPDATE user_tenant_roles 
            SET organization_id = tenant_id 
            WHERE organization_id IS NULL AND tenant_id IS NOT NULL;
            
            ALTER TABLE user_tenant_roles DROP COLUMN tenant_id;
            RAISE NOTICE 'Dropped tenant_id column';
        ELSE
            RAISE NOTICE 'tenant_id does not exist. Migration already complete.';
        END IF;
    ELSE
        RAISE NOTICE 'Neither tenant_id nor organization_id found. Table may be empty or have different structure.';
    END IF;
END $$;

-- Verify the final state
SELECT 
    'user_tenant_roles columns:' as info,
    string_agg(column_name, ', ' ORDER BY ordinal_position) as columns
FROM information_schema.columns
WHERE table_name = 'user_tenant_roles';

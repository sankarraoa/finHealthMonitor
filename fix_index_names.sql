-- Fix index names to match the new column names
-- This is optional but improves consistency

-- Fix index name in tenant_roles table
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE indexname = 'ix_tenant_roles_tenant_id'
        AND tablename = 'tenant_roles'
    ) THEN
        -- Drop the old index and create a new one with correct name
        DROP INDEX IF EXISTS ix_tenant_roles_tenant_id;
        
        -- Check if the new index already exists
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes 
            WHERE indexname = 'ix_tenant_roles_organization_id'
            AND tablename = 'tenant_roles'
        ) THEN
            CREATE INDEX ix_tenant_roles_organization_id ON tenant_roles(organization_id);
            RAISE NOTICE 'Created index ix_tenant_roles_organization_id';
        ELSE
            RAISE NOTICE 'Index ix_tenant_roles_organization_id already exists';
        END IF;
    ELSE
        RAISE NOTICE 'Index ix_tenant_roles_tenant_id does not exist, skipping';
    END IF;
END $$;

-- Verify final state
SELECT 
    'Indexes on tenant_roles:' as info,
    string_agg(indexname, ', ' ORDER BY indexname) as indexes
FROM pg_indexes
WHERE tablename = 'tenant_roles';

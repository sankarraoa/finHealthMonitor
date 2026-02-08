-- Check current structure of tenant_roles and user_tenant_roles tables

-- Check tenant_roles table
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'tenant_roles'
ORDER BY ordinal_position;

-- Check user_tenant_roles table
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'user_tenant_roles'
ORDER BY ordinal_position;

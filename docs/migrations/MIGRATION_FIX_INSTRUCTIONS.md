# Fix Migration Issue

The migration partially succeeded. The error indicates that `user_tenant_roles` table already has an `organization_id` column, which prevented the rename operation.

## Current Status

From the migration output:
- ✅ `tenant_roles` table: Successfully renamed `tenant_id` → `organization_id`
- ⚠️ `user_tenant_roles` table: `organization_id` already exists, but `tenant_id` may still exist

## Solution

Run the fix script to handle the duplicate column situation:

```bash
psql finhealthmonitor -f fix_migration_issue.sql
```

This script will:
1. Check if both `tenant_id` and `organization_id` exist
2. Copy any data from `tenant_id` to `organization_id` (where `organization_id` is NULL)
3. Drop the `tenant_id` column

## Verify Migration

After running the fix, verify the migration is complete:

```sql
-- Connect to database
psql finhealthmonitor

-- Check tenant_roles structure
\d tenant_roles
-- Should show: organization_id (NOT tenant_id)

-- Check user_tenant_roles structure  
\d user_tenant_roles
-- Should show: organization_id (NOT tenant_id)
```

Or run this query:
```sql
SELECT 
    table_name,
    column_name
FROM information_schema.columns
WHERE table_name IN ('tenant_roles', 'user_tenant_roles')
    AND column_name IN ('tenant_id', 'organization_id')
ORDER BY table_name, column_name;
```

**Expected result:**
- Both tables should have `organization_id`
- Neither table should have `tenant_id`

## If Issues Persist

If you still see `tenant_id` columns, you can manually drop them:

```sql
-- Only run if tenant_id still exists
ALTER TABLE user_tenant_roles DROP COLUMN IF EXISTS tenant_id;
ALTER TABLE tenant_roles DROP COLUMN IF EXISTS tenant_id;
```

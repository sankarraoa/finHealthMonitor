-- Fix organizations table: Set tenant_id to NULL for organizations that are also tenants
-- This ensures that tenants don't reference themselves

-- ============================================================================
-- Update existing organizations that are also tenants
-- ============================================================================
UPDATE organizations o
SET tenant_id = NULL
WHERE EXISTS (
    SELECT 1 
    FROM tenants t 
    WHERE t.id = o.party_id
);

-- ============================================================================
-- Recreate triggers with the corrected logic
-- ============================================================================

-- Drop existing triggers
DROP TRIGGER IF EXISTS trigger_create_organization_on_party_insert ON parties;
DROP TRIGGER IF EXISTS trigger_update_organization_on_party_update ON parties;

-- Drop existing functions
DROP FUNCTION IF EXISTS create_organization_on_party_insert();
DROP FUNCTION IF EXISTS update_organization_on_party_update();

-- Recreate function for insert
CREATE OR REPLACE FUNCTION create_organization_on_party_insert()
RETURNS TRIGGER AS $$
DECLARE
    org_tenant_id VARCHAR;
BEGIN
    IF NEW.party_type = 'organization' THEN
        -- If this party IS a tenant (exists in tenants table), set tenant_id to NULL
        -- Otherwise, use the tenant_id from the parties table
        IF EXISTS (SELECT 1 FROM tenants WHERE id = NEW.id) THEN
            org_tenant_id := NULL;
        ELSE
            org_tenant_id := NEW.tenant_id;
        END IF;
        
        INSERT INTO organizations (party_id, name, tenant_id, created_by, modified_by)
        VALUES (NEW.id, NEW.name, org_tenant_id, NEW.created_by, NEW.modified_by)
        ON CONFLICT (party_id) DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recreate function for update
CREATE OR REPLACE FUNCTION update_organization_on_party_update()
RETURNS TRIGGER AS $$
DECLARE
    org_tenant_id VARCHAR;
BEGIN
    IF NEW.party_type = 'organization' THEN
        -- If this party IS a tenant (exists in tenants table), set tenant_id to NULL
        -- Otherwise, use the tenant_id from the parties table
        IF EXISTS (SELECT 1 FROM tenants WHERE id = NEW.id) THEN
            org_tenant_id := NULL;
        ELSE
            org_tenant_id := NEW.tenant_id;
        END IF;
        
        UPDATE organizations
        SET 
            name = NEW.name,
            tenant_id = org_tenant_id,
            created_by = NEW.created_by,
            modified_by = NEW.modified_by
        WHERE party_id = NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recreate triggers
CREATE TRIGGER trigger_create_organization_on_party_insert
    AFTER INSERT ON parties
    FOR EACH ROW
    WHEN (NEW.party_type = 'organization')
    EXECUTE FUNCTION create_organization_on_party_insert();

CREATE TRIGGER trigger_update_organization_on_party_update
    AFTER UPDATE ON parties
    FOR EACH ROW
    WHEN (NEW.party_type = 'organization')
    EXECUTE FUNCTION update_organization_on_party_update();

-- ============================================================================
-- Verification
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE '✓ Updated organizations table: tenant_id set to NULL for organizations that are also tenants';
    RAISE NOTICE '✓ Recreated triggers with corrected logic';
END $$;

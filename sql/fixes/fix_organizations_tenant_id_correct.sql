-- Fix organizations table: Set tenant_id to the tenant from parties.tenant_id
-- Even if the organization party IS also a tenant, the organization still belongs to that tenant

-- ============================================================================
-- Update organizations to set tenant_id from parties.tenant_id
-- ============================================================================
UPDATE organizations o
SET tenant_id = p.tenant_id
FROM parties p
WHERE o.party_id = p.id
  AND p.tenant_id IS NOT NULL
  AND o.tenant_id IS NULL;

-- Also update organizations that have tenant_id but it might be wrong
UPDATE organizations o
SET tenant_id = p.tenant_id
FROM parties p
WHERE o.party_id = p.id
  AND p.tenant_id IS NOT NULL;

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
-- Organizations always get tenant_id from parties.tenant_id
CREATE OR REPLACE FUNCTION create_organization_on_party_insert()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.party_type = 'organization' THEN
        INSERT INTO organizations (party_id, name, tenant_id, created_by, modified_by)
        VALUES (NEW.id, NEW.name, NEW.tenant_id, NEW.created_by, NEW.modified_by)
        ON CONFLICT (party_id) DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recreate function for update
-- Organizations always get tenant_id from parties.tenant_id
CREATE OR REPLACE FUNCTION update_organization_on_party_update()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.party_type = 'organization' THEN
        UPDATE organizations
        SET 
            name = NEW.name,
            tenant_id = NEW.tenant_id,
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
    RAISE NOTICE '✓ Updated organizations table: tenant_id set from parties.tenant_id';
    RAISE NOTICE '✓ Recreated triggers with corrected logic';
END $$;

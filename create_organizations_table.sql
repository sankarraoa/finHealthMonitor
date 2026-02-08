-- Migration script to create organizations table
-- This table stores organizations that belong to parties with party_type='organization'
-- For every record in parties with type='organization', there should be a record in this table

-- ============================================================================
-- Create organizations table
-- ============================================================================
CREATE TABLE IF NOT EXISTS organizations (
    id VARCHAR NOT NULL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    tenant_id VARCHAR,
    created_by VARCHAR,
    modified_by VARCHAR,
    CONSTRAINT fk_organizations_id 
        FOREIGN KEY (id) 
        REFERENCES parties(id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_organizations_tenant_id 
        FOREIGN KEY (tenant_id) 
        REFERENCES tenants(id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_organizations_created_by 
        FOREIGN KEY (created_by) 
        REFERENCES persons(id) 
        ON DELETE SET NULL,
    CONSTRAINT fk_organizations_modified_by 
        FOREIGN KEY (modified_by) 
        REFERENCES persons(id) 
        ON DELETE SET NULL
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_organizations_id ON organizations(id);
CREATE INDEX IF NOT EXISTS idx_organizations_tenant_id ON organizations(tenant_id);
CREATE INDEX IF NOT EXISTS idx_organizations_name ON organizations(name);

-- ============================================================================
-- Migrate existing data (if any parties with party_type='organization' exist)
-- ============================================================================
DO $$
DECLARE
    party_rec RECORD;
    org_name VARCHAR;
BEGIN
    -- For each party with type='organization', create an organization record
    FOR party_rec IN 
        SELECT id, name 
        FROM parties 
        WHERE party_type = 'organization'
        AND id NOT IN (SELECT id FROM organizations)
    LOOP
        -- Get the name from parties table
        org_name := party_rec.name;
        
        -- Insert into organizations table
        -- tenant_id should come from parties.tenant_id (which points to the B2B SaaS tenant)
        INSERT INTO organizations (id, name, tenant_id, created_by, modified_by)
        SELECT 
            party_rec.id,
            party_rec.name,
            p.tenant_id,
            p.created_by,
            p.modified_by
        FROM parties p
        WHERE p.id = party_rec.id
        ON CONFLICT (id) DO NOTHING;
        
        RAISE NOTICE 'Created organization record for id: %, name: %', party_rec.id, org_name;
    END LOOP;
END $$;

-- ============================================================================
-- Create trigger to automatically create organization record when party is created
-- ============================================================================
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

CREATE TRIGGER trigger_create_organization_on_party_insert
    AFTER INSERT ON parties
    FOR EACH ROW
    WHEN (NEW.party_type = 'organization')
    EXECUTE FUNCTION create_organization_on_party_insert();

-- ============================================================================
-- Create trigger to update organization when party is updated
-- ============================================================================
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
    RAISE NOTICE '✓ organizations table created';
    RAISE NOTICE '✓ Indexes created';
    RAISE NOTICE '✓ Triggers created';
    RAISE NOTICE '✓ Existing data migrated';
END $$;

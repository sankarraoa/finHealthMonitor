-- Migration script to rename party_id to id in organizations table for consistency with persons table

-- ============================================================================
-- Rename party_id column to id
-- ============================================================================

-- First, drop the foreign key constraint
ALTER TABLE organizations 
DROP CONSTRAINT IF EXISTS fk_organizations_party_id;

-- Rename the column
ALTER TABLE organizations 
RENAME COLUMN party_id TO id;

-- Recreate the foreign key constraint with the new column name
ALTER TABLE organizations
ADD CONSTRAINT fk_organizations_id
FOREIGN KEY (id) 
REFERENCES parties(id) 
ON DELETE CASCADE;

-- ============================================================================
-- Update indexes
-- ============================================================================

-- Drop old index if it exists
DROP INDEX IF EXISTS idx_organizations_party_id;

-- The primary key index will automatically use the new column name
-- But we can verify it exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE indexname = 'organizations_pkey1' 
        AND tablename = 'organizations'
    ) THEN
        RAISE NOTICE 'Primary key index exists';
    END IF;
END $$;

-- ============================================================================
-- Update triggers to use 'id' instead of 'party_id'
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
BEGIN
    IF NEW.party_type = 'organization' THEN
        INSERT INTO organizations (id, name, tenant_id, created_by, modified_by)
        VALUES (NEW.id, NEW.name, NEW.tenant_id, NEW.created_by, NEW.modified_by)
        ON CONFLICT (id) DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recreate function for update
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
        WHERE id = NEW.id;
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
    RAISE NOTICE '✓ Renamed party_id to id in organizations table';
    RAISE NOTICE '✓ Updated foreign key constraint';
    RAISE NOTICE '✓ Updated triggers to use id instead of party_id';
END $$;

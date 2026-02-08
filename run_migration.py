#!/usr/bin/env python3
"""Script to run the SQL migration to rename tenant_id to organization_id.
   
   Usage: python3 run_migration.py
   Make sure you're in the virtual environment: source venv/bin/activate
"""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(__file__))

try:
    from app.database import engine
    from sqlalchemy import text
    import logging
except ImportError as e:
    print("❌ Error: Missing dependencies. Please activate your virtual environment:")
    print("   source venv/bin/activate")
    print(f"   Error: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """Run the migration script."""
    migration_file = "rename_tenant_id_to_organization_id.sql"
    
    if not os.path.exists(migration_file):
        logger.error(f"Migration file not found: {migration_file}")
        sys.exit(1)
    
    # Read the migration SQL
    with open(migration_file, 'r') as f:
        migration_sql = f.read()
    
    logger.info("Starting migration: rename tenant_id to organization_id")
    logger.info(f"Using database: {engine.url}")
    
    try:
        with engine.connect() as conn:
            # Execute the migration
            # Split by semicolons and execute each statement
            statements = [s.strip() for s in migration_sql.split(';') if s.strip() and not s.strip().startswith('--')]
            
            for statement in statements:
                if statement:
                    try:
                        logger.info(f"Executing: {statement[:100]}...")
                        conn.execute(text(statement))
                        conn.commit()
                        logger.info("✓ Success")
                    except Exception as e:
                        # Some statements might fail if constraints/indexes don't exist
                        if "does not exist" in str(e).lower() or "already exists" in str(e).lower():
                            logger.warning(f"⚠ Skipped (expected): {str(e)[:100]}")
                        else:
                            logger.error(f"✗ Error: {e}")
                            raise
        
        logger.info("✅ Migration completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migration()

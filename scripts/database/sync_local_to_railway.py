#!/usr/bin/env python3
"""Sync local database schema and data to Railway PostgreSQL."""
import psycopg2
from psycopg2.extras import execute_batch, Json
import sys
import os
import json
import subprocess
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database URLs from config
from app.config import config

LOCAL_URL = config.LOCAL_DATABASE_URL
RAILWAY_URL = config.RAILWAY_DATABASE_URL

# Table copy order (respecting foreign key dependencies)
# Order matters: parent tables first, then child tables
# Note: Local 'tenants' table (B2B SaaS tenants) maps to Railway 'organizations' table
#       Local 'organizations' table (old structure) should be ignored
TABLES = [
    'parties',              # Base table, no dependencies - must be first
    ('tenants', 'organizations'),  # Local 'tenants' (B2B SaaS) -> Railway 'organizations'
    'persons',              # Depends on parties
    'permissions',          # No dependencies
    'tenant_roles',         # Depends on organizations
    'user_tenant_roles',    # Depends on persons, organizations, tenant_roles
    'role_permissions',     # Depends on tenant_roles, permissions
    'connections',          # Depends on organizations
    'xero_tenants',         # Depends on connections
    'payroll_risk_analyses', # References connections (no FK constraint)
    'mcp_data_cache',       # Depends on connections
]

def get_table_columns(cursor, table_name):
    """Get column names and types for a table."""
    cursor.execute(f"""
        SELECT column_name, data_type, udt_name
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = %s
        ORDER BY ordinal_position;
    """, (table_name,))
    return cursor.fetchall()

def get_column_info(cursor, table_name):
    """Get column names and their data types."""
    columns = get_table_columns(cursor, table_name)
    column_names = [col[0] for col in columns]
    # Check for JSON/JSONB columns
    json_columns = {col[0] for col in columns if col[1] in ('json', 'jsonb') or col[2] in ('json', 'jsonb')}
    return column_names, json_columns

def get_row_count(cursor, table_name):
    """Get row count for a table."""
    cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
    return cursor.fetchone()[0]

def get_all_tables(cursor):
    """Get all table names in the database."""
    cursor.execute("""
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename NOT LIKE 'alembic_%'
        ORDER BY tablename;
    """)
    return [row[0] for row in cursor.fetchall()]

def drop_all_tables(conn):
    """Drop all tables in Railway database (fresh start)."""
    cursor = conn.cursor()
    try:
        # Disable foreign key checks temporarily
        cursor.execute("SET session_replication_role = 'replica';")
        
        # Get all table names
        tables = get_all_tables(cursor)
        
        if tables:
            print(f"\n🗑️  Dropping {len(tables)} tables in Railway database...")
            for table in tables:
                cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
                print(f"   ✅ Dropped {table}")
            conn.commit()
        else:
            print("\nℹ️  No tables to drop in Railway database")
        
        # Re-enable foreign key checks
        cursor.execute("SET session_replication_role = 'origin';")
        
    except psycopg2.Error as e:
        conn.rollback()
        print(f"❌ Error dropping tables: {e}")
        raise
    finally:
        cursor.close()

def copy_tenants_to_organizations(source_conn, dest_conn):
    """Special handler to copy local 'tenants' table to Railway 'organizations' table.
    
    This also ensures corresponding 'parties' entries are created.
    """
    source_cursor = source_conn.cursor()
    dest_cursor = dest_conn.cursor()
    
    try:
        # Check if source table exists
        source_cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'tenants'
            );
        """, ())
        
        if not source_cursor.fetchone()[0]:
            print(f"   ⚠️  Table 'tenants' does not exist in local database, skipping...")
            return 0
        
        # Get row count
        source_cursor.execute("SELECT COUNT(*) FROM tenants;")
        source_count = source_cursor.fetchone()[0]
        
        if source_count == 0:
            print(f"   ℹ️  Table 'tenants' is empty, skipping...")
            return 0
        
        print(f"   📊 Found {source_count} rows in local 'tenants' (copying to 'organizations')")
        
        # Get all rows from local tenants
        source_cursor.execute("SELECT * FROM tenants;")
        tenant_rows = source_cursor.fetchall()
        tenant_cols = [desc[0] for desc in source_cursor.description]
        
        # Get organizations table structure in Railway
        dest_cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'organizations'
            ORDER BY ordinal_position;
        """)
        org_cols = [row[0] for row in dest_cursor.fetchall()]
        
        # Common columns between local tenants and Railway organizations
        common_cols = [col for col in tenant_cols if col in org_cols and col != 'id']
        # id is special - we'll use it for both parties and organizations
        
        inserted_count = 0
        now = __import__('datetime').datetime.utcnow().isoformat()
        
        for tenant_row in tenant_rows:
            tenant_data = dict(zip(tenant_cols, tenant_row))
            tenant_id = tenant_data['id']
            
            try:
                # First, ensure parties entry exists
                dest_cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM parties WHERE id = %s
                    );
                """, (tenant_id,))
                
                if not dest_cursor.fetchone()[0]:
                    # Create parties entry
                    # Get name from company_name or use a default
                    name = tenant_data.get('company_name', 'Unknown Organization')
                    dest_cursor.execute("""
                        INSERT INTO parties (id, party_type, name, created_at, updated_at)
                        VALUES (%s, 'organization', %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING;
                    """, (tenant_id, name, now, now))
                
                # Now insert/update organizations entry
                # Build column list and values
                org_cols_to_insert = ['id'] + common_cols
                org_values = [tenant_id] + [tenant_data.get(col) for col in common_cols]
                org_placeholders = ', '.join(['%s'] * len(org_values))
                org_cols_str = ', '.join(org_cols_to_insert)
                
                dest_cursor.execute(f"""
                    INSERT INTO organizations ({org_cols_str})
                    VALUES ({org_placeholders})
                    ON CONFLICT (id) DO UPDATE SET
                        company_name = EXCLUDED.company_name,
                        tax_id = EXCLUDED.tax_id,
                        address = EXCLUDED.address,
                        phone = EXCLUDED.phone,
                        email = EXCLUDED.email,
                        is_active = EXCLUDED.is_active;
                """, org_values)
                
                inserted_count += 1
                print(f"   📦 Copied {inserted_count}/{source_count} organizations...", end='\r')
                
            except Exception as e:
                print(f"   ⚠️  Error copying tenant {tenant_id}: {e}")
                continue
        
        dest_conn.commit()
        print(f"   ✅ Copied {inserted_count} organizations from 'tenants' to 'organizations'")
        
        return inserted_count
        
    except Exception as e:
        dest_conn.rollback()
        print(f"   ❌ Error copying tenants to organizations: {e}")
        raise
    finally:
        source_cursor.close()
        dest_cursor.close()

def copy_table(source_conn, dest_conn, source_table, dest_table=None):
    """Copy data from source to destination table.
    
    Args:
        source_conn: Source database connection
        dest_conn: Destination database connection
        source_table: Source table name (or tuple of (source, dest) for mapping)
        dest_table: Destination table name (if different from source)
    """
    # Handle table mapping (source_table can be a tuple)
    if isinstance(source_table, tuple):
        source_table, dest_table = source_table
    else:
        dest_table = dest_table or source_table
    
    source_cursor = source_conn.cursor()
    dest_cursor = dest_conn.cursor()
    
    try:
        # Check if table exists in source
        source_cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = %s
            );
        """, (source_table,))
        
        if not source_cursor.fetchone()[0]:
            print(f"   ⚠️  Table '{source_table}' does not exist in local database, skipping...")
            return 0
        
        # Check if destination table exists
        dest_cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = %s
            );
        """, (dest_table,))
        if not dest_cursor.fetchone()[0]:
            print(f"   ⚠️  Table '{dest_table}' does not exist in Railway database, skipping...")
            return 0
        
        # Get row count from source
        source_count = get_row_count(source_cursor, source_table)
        
        if source_count == 0:
            print(f"   ℹ️  Table '{source_table}' is empty, skipping...")
            return 0
        
        if source_table != dest_table:
            print(f"   📊 Found {source_count} rows in local '{source_table}' (copying to '{dest_table}')")
        else:
            print(f"   📊 Found {source_count} rows in local '{source_table}'")
        
        # Get column names and JSON column info from both source and destination
        source_columns, source_json_columns = get_column_info(source_cursor, source_table)
        dest_columns, dest_json_columns = get_column_info(dest_cursor, dest_table)
        
        if not source_columns:
            print(f"   ⚠️  No columns found for '{table_name}' in source, skipping...")
            return 0
        
        if not dest_columns:
            print(f"   ⚠️  No columns found for '{table_name}' in destination, skipping...")
            return 0
        
        # Find common columns (columns that exist in both source and destination)
        common_columns = [col for col in source_columns if col in dest_columns]
        missing_in_dest = [col for col in source_columns if col not in dest_columns]
        missing_in_source = [col for col in dest_columns if col not in source_columns]
        
        if missing_in_dest:
            print(f"   ⚠️  Columns in local but not in Railway (will be skipped): {missing_in_dest}")
        if missing_in_source:
            print(f"   ⚠️  Columns in Railway but not in local (will be NULL): {missing_in_source}")
        
        if not common_columns:
            print(f"   ⚠️  No common columns between source and destination, skipping...")
            return 0
        
        # Use only common columns for copying
        columns = common_columns
        json_columns = {col for col in common_columns if col in source_json_columns or col in dest_json_columns}
        
        # Build SELECT and INSERT queries using only common columns
        columns_str = ', '.join(columns)
        placeholders = ', '.join(['%s'] * len(columns))
        select_query = f"SELECT {columns_str} FROM {source_table};"
        insert_query = f"INSERT INTO {dest_table} ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING;"
        
        # Fetch all data from source
        source_cursor.execute(select_query)
        rows = source_cursor.fetchall()
        
        # Convert JSON columns to proper format for psycopg2
        processed_rows = []
        for row in rows:
            processed_row = []
            for i, value in enumerate(row):
                col_name = columns[i]
                if col_name in json_columns and value is not None:
                    # If it's already a dict/list, convert to Json wrapper
                    if isinstance(value, (dict, list)):
                        processed_row.append(Json(value))
                    elif isinstance(value, str):
                        # Try to parse as JSON, if valid keep as string, otherwise wrap
                        try:
                            json.loads(value)
                            processed_row.append(value)
                        except (json.JSONDecodeError, TypeError):
                            processed_row.append(Json(value))
                    else:
                        processed_row.append(Json(value))
                else:
                    processed_row.append(value)
            processed_rows.append(tuple(processed_row))
        
        rows = processed_rows
        
        if not rows:
            print(f"   ℹ️  No rows to copy from '{source_table}'")
            return 0
        
        # Insert into destination in batches
        batch_size = 100
        inserted_count = 0
        
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            execute_batch(dest_cursor, insert_query, batch, page_size=batch_size)
            inserted_count += len(batch)
            print(f"   📦 Copied {inserted_count}/{len(rows)} rows...", end='\r')
        
        dest_conn.commit()
        if source_table != dest_table:
            print(f"   ✅ Copied {inserted_count} rows from '{source_table}' to '{dest_table}'")
        else:
            print(f"   ✅ Copied {inserted_count} rows from '{source_table}'")
        
        return inserted_count
        
    except psycopg2.Error as e:
        dest_conn.rollback()
        print(f"   ❌ Error copying '{source_table}' to '{dest_table}': {e}")
        raise
    finally:
        source_cursor.close()
        dest_cursor.close()

def main():
    """Main function to sync local database to Railway."""
    print("🔄 Syncing Local PostgreSQL to Railway PostgreSQL")
    print("=" * 70)
    print("\n⚠️  WARNING: This will:")
    print("   1. Drop ALL tables in Railway database")
    print("   2. Apply all Alembic migrations to Railway")
    print("   3. Copy all data from local to Railway")
    print("\n   This is a DESTRUCTIVE operation on Railway database!")
    
    # Check for --yes flag to skip confirmation
    skip_confirmation = '--yes' in sys.argv or '-y' in sys.argv
    
    if not skip_confirmation:
        response = input("\n   Continue? (yes/no): ").strip().lower()
        if response != 'yes':
            print("❌ Aborted.")
            sys.exit(0)
    else:
        print("\n   ⚡ Auto-confirming (--yes flag provided)")
    
    # Connect to databases
    try:
        print("\n🔌 Connecting to local database...")
        local_conn = psycopg2.connect(LOCAL_URL)
        print("   ✅ Connected to local database")
        
        print("\n🔌 Connecting to Railway database...")
        railway_conn = psycopg2.connect(RAILWAY_URL)
        print("   ✅ Connected to Railway database")
        
    except psycopg2.Error as e:
        print(f"\n❌ Connection error: {e}")
        sys.exit(1)
    
    try:
        # Step 1: Drop all tables in Railway
        drop_all_tables(railway_conn)
        
        # Step 2: Apply migrations to Railway using SQL script
        print("\n📦 Applying migrations to Railway...")
        try:
            # Read and execute SQL migration script
            sql_file = os.path.join(os.path.dirname(__file__), 'apply_railway_migrations.sql')
            if not os.path.exists(sql_file):
                print(f"   ⚠️  SQL migration file not found: {sql_file}")
                print("   Attempting to use Alembic instead...")
                env = os.environ.copy()
                env["USE_LOCAL_DB"] = "false"
                result = subprocess.run(
                    ["alembic", "upgrade", "head"],
                    env=env,
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    print(f"❌ Migration failed!")
                    print(f"STDOUT: {result.stdout}")
                    print(f"STDERR: {result.stderr}")
                    sys.exit(1)
            else:
                with open(sql_file, 'r') as f:
                    sql = f.read()
                # Remove BEGIN/COMMIT since we'll handle transactions
                sql_lines = [line for line in sql.split('\n') if not line.strip().upper() in ['BEGIN;', 'COMMIT;']]
                sql = '\n'.join(sql_lines)
                
                railway_cursor = railway_conn.cursor()
                railway_cursor.execute(sql)
                railway_conn.commit()
                railway_cursor.close()
                print("   ✅ Migrations applied successfully using SQL script")
        except Exception as e:
            print(f"   ❌ Error applying migrations: {e}")
            railway_conn.rollback()
            sys.exit(1)
        
        # Verify tables were actually created
        railway_cursor = railway_conn.cursor()
        railway_cursor.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public' 
            AND tablename NOT LIKE 'alembic_%'
            ORDER BY tablename;
        """)
        created_tables = [row[0] for row in railway_cursor.fetchall()]
        railway_cursor.close()
        
        if len(created_tables) == 0:
            print("   ⚠️  Warning: No tables were created by migrations!")
            print("   This might indicate a migration issue. Continuing anyway...")
        else:
            print(f"   ✅ Verified {len(created_tables)} tables exist in Railway")
        
        # Step 3: Get actual tables from local database (in case some don't exist)
        local_cursor = local_conn.cursor()
        local_tables = get_all_tables(local_cursor)
        local_cursor.close()
        
        # Filter TABLES list to only include tables that exist
        # Handle both string table names and tuples (source, dest)
        tables_to_copy = []
        for t in TABLES:
            if isinstance(t, tuple):
                source_table = t[0]
                if source_table in local_tables:
                    tables_to_copy.append(t)
            else:
                if t in local_tables:
                    tables_to_copy.append(t)
        
        if len(tables_to_copy) < len(TABLES):
            missing = [t for t in TABLES if t not in tables_to_copy]
            print(f"\n⚠️  Some tables from expected list don't exist: {missing}")
        
        # Step 4: Copy data from local to Railway
        print("\n📦 Copying data from local to Railway...")
        print("-" * 70)
        
        total_copied = 0
        for table_name in tables_to_copy:
            print(f"\n📋 Copying table: {table_name}")
            try:
                # Special handling for tenants -> organizations mapping
                if isinstance(table_name, tuple) and table_name[0] == 'tenants' and table_name[1] == 'organizations':
                    count = copy_tenants_to_organizations(local_conn, railway_conn)
                else:
                    if isinstance(table_name, tuple):
                        count = copy_table(local_conn, railway_conn, table_name[0], table_name[1])
                    else:
                        count = copy_table(local_conn, railway_conn, table_name)
                total_copied += count
            except Exception as e:
                print(f"   ❌ Failed to copy '{table_name}': {e}")
                # Continue with other tables
                continue
        
        print("\n" + "=" * 70)
        print(f"✅ Sync completed! Total rows copied: {total_copied}")
        print("\n💡 Railway database is now in sync with your local database.")
        print("   You can now set USE_LOCAL_DB=false to use Railway.")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Sync interrupted by user.")
        railway_conn.rollback()
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        railway_conn.rollback()
        raise
    finally:
        local_conn.close()
        railway_conn.close()
        print("\n🔌 Database connections closed.")

if __name__ == "__main__":
    main()

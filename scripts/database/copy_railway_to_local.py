#!/usr/bin/env python3
"""One-time script to copy data from Railway PostgreSQL to local PostgreSQL."""
import psycopg2
from psycopg2.extras import execute_batch, Json
import sys
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database URLs from config
from app.config import config

RAILWAY_URL = config.RAILWAY_DATABASE_URL
LOCAL_URL = config.LOCAL_DATABASE_URL

# Table copy order (respecting foreign key dependencies)
TABLES = [
    'connections',           # No dependencies
    'tenants',              # Depends on connections
    'payroll_risk_analyses', # No foreign keys, but references connection_id
    'mcp_data_cache',        # Depends on connections
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

def copy_table(source_conn, dest_conn, table_name, clear_first=False):
    """Copy data from source to destination table."""
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
        """, (table_name,))
        
        if not source_cursor.fetchone()[0]:
            print(f"   ⚠️  Table '{table_name}' does not exist in Railway database, skipping...")
            return 0
        
        # Get row count from source
        source_count = get_row_count(source_cursor, table_name)
        
        if source_count == 0:
            print(f"   ℹ️  Table '{table_name}' is empty in Railway database, skipping...")
            return 0
        
        print(f"   📊 Found {source_count} rows in Railway '{table_name}'")
        
        # Clear destination table if requested
        if clear_first:
            dest_cursor.execute(f"TRUNCATE TABLE {table_name} CASCADE;")
            print(f"   🗑️  Cleared existing data from local '{table_name}'")
        
        # Get column names and JSON column info
        columns, json_columns = get_column_info(source_cursor, table_name)
        if not columns:
            print(f"   ⚠️  No columns found for '{table_name}', skipping...")
            return 0
        
        # Build SELECT and INSERT queries
        columns_str = ', '.join(columns)
        placeholders = ', '.join(['%s'] * len(columns))
        select_query = f"SELECT {columns_str} FROM {table_name};"
        insert_query = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING;"
        
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
                    # If it's already a dict/list, convert to JSON string
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
            print(f"   ℹ️  No rows to copy from '{table_name}'")
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
        print(f"   ✅ Copied {inserted_count} rows from '{table_name}'")
        
        return inserted_count
        
    except psycopg2.Error as e:
        dest_conn.rollback()
        print(f"   ❌ Error copying '{table_name}': {e}")
        raise
    finally:
        source_cursor.close()
        dest_cursor.close()

def main():
    """Main function to copy data from Railway to local database."""
    print("🔄 Copying data from Railway PostgreSQL to Local PostgreSQL")
    print("=" * 70)
    
    # Connect to databases
    try:
        print("\n🔌 Connecting to Railway database...")
        railway_conn = psycopg2.connect(RAILWAY_URL)
        print("   ✅ Connected to Railway")
        
        print("\n🔌 Connecting to local database...")
        local_conn = psycopg2.connect(LOCAL_URL)
        print("   ✅ Connected to local database")
        
    except psycopg2.Error as e:
        print(f"\n❌ Connection error: {e}")
        sys.exit(1)
    
    # Ask user if they want to clear existing data
    print("\n⚠️  WARNING: This will copy data from Railway to your local database.")
    print("   If tables already have data locally, you can:")
    print("   1. Clear local data first (recommended for first-time copy)")
    print("   2. Keep local data (will skip duplicates)")
    
    response = input("\n   Clear local data first? (y/N): ").strip().lower()
    clear_first = response == 'y'
    
    if clear_first:
        print("\n🗑️  Will clear local data before copying...")
    else:
        print("\n📋 Will keep existing local data (duplicates will be skipped)...")
    
    # Copy each table
    total_copied = 0
    print("\n📦 Starting data copy...")
    print("-" * 70)
    
    try:
        for table_name in TABLES:
            print(f"\n📋 Copying table: {table_name}")
            try:
                count = copy_table(railway_conn, local_conn, table_name, clear_first=clear_first)
                total_copied += count
            except Exception as e:
                print(f"   ❌ Failed to copy '{table_name}': {e}")
                # Continue with other tables
                continue
        
        print("\n" + "=" * 70)
        print(f"✅ Data copy completed! Total rows copied: {total_copied}")
        print("\n💡 Your local database now has the data from Railway.")
        print("   You can now use USE_LOCAL_DB=true for faster development!")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Copy interrupted by user. Some data may have been copied.")
        local_conn.rollback()
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        local_conn.rollback()
    finally:
        railway_conn.close()
        local_conn.close()
        print("\n🔌 Database connections closed.")

if __name__ == "__main__":
    main()

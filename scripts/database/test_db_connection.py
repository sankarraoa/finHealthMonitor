#!/usr/bin/env python3
"""Test script to verify Railway PostgreSQL connection."""
import psycopg2
import sys
import re

DATABASE_URL = "postgresql://postgres:nIrSLrxNUhzPghZJiuKVwGwcFMxiAzgh@metro.proxy.rlwy.net:10176/railway"

def test_connection():
    """Test PostgreSQL connection."""
    try:
        print("🔌 Attempting to connect to Railway PostgreSQL...")
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Test basic query - Full version
        cursor.execute("SELECT version();")
        version_full = cursor.fetchone()[0]
        print(f"✅ Successfully connected to PostgreSQL!")
        print(f"   Full Version: {version_full}")
        
        # Get server version number
        cursor.execute("SHOW server_version;")
        server_version = cursor.fetchone()[0]
        print(f"   Server Version: {server_version}")
        
        # Extract major version
        major_version = server_version.split('.')[0]
        print(f"   Major Version: PostgreSQL {major_version}")
        
        # Test database name
        cursor.execute("SELECT current_database();")
        db_name = cursor.fetchone()
        print(f"   Database: {db_name[0]}")
        
        # Check if tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()
        
        if tables:
            print(f"\n📊 Existing tables in database:")
            for table in tables:
                print(f"   - {table[0]}")
        else:
            print(f"\n📊 No tables found in database (empty database)")
        
        cursor.close()
        conn.close()
        print("\n✅ Connection test completed successfully!")
        print(f"\n💡 Install PostgreSQL {major_version} locally to match Railway version")
        return True
        
    except psycopg2.OperationalError as e:
        print(f"❌ Connection failed: {e}")
        print("\nPossible issues:")
        print("  - Network connectivity")
        print("  - Incorrect credentials")
        print("  - Database server not accessible")
        return False
    except ImportError:
        print("❌ psycopg2 not installed. Please install it:")
        print("   pip install psycopg2-binary")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)

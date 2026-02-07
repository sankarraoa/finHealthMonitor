#!/usr/bin/env python3
"""Script to create payroll_risk_analyses table in Railway PostgreSQL."""
import psycopg2
import sys

DATABASE_URL = "postgresql://postgres:nIrSLrxNUhzPghZJiuKVwGwcFMxiAzgh@metro.proxy.rlwy.net:10176/railway"

def create_tables():
    """Create payroll_risk_analyses table and indexes."""
    try:
        print("🔌 Connecting to Railway PostgreSQL...")
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        print("📋 Creating payroll_risk_analyses table...")
        
        # Create the table (matching SQLite schema)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payroll_risk_analyses (
                id TEXT PRIMARY KEY,
                connection_id TEXT NOT NULL,
                connection_name TEXT NOT NULL,
                tenant_id TEXT,
                tenant_name TEXT,
                status TEXT NOT NULL,
                initiated_at TEXT NOT NULL,
                completed_at TEXT,
                result_data TEXT,
                error_message TEXT,
                progress INTEGER DEFAULT 0,
                progress_message TEXT
            );
        """)
        
        print("✅ Table 'payroll_risk_analyses' created successfully!")
        
        # Create indexes
        print("📊 Creating indexes...")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_connection_id 
            ON payroll_risk_analyses(connection_id);
        """)
        print("   ✅ Index 'idx_connection_id' created")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_status 
            ON payroll_risk_analyses(status);
        """)
        print("   ✅ Index 'idx_status' created")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_initiated_at 
            ON payroll_risk_analyses(initiated_at DESC);
        """)
        print("   ✅ Index 'idx_initiated_at' created")
        
        # Commit changes
        conn.commit()
        
        # Verify table was created
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'payroll_risk_analyses'
            ORDER BY ordinal_position;
        """)
        columns = cursor.fetchall()
        
        print(f"\n📋 Table structure:")
        for col in columns:
            nullable = "NULL" if col[2] == "YES" else "NOT NULL"
            print(f"   - {col[0]}: {col[1]} ({nullable})")
        
        # Check indexes
        cursor.execute("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'payroll_risk_analyses'
            ORDER BY indexname;
        """)
        indexes = cursor.fetchall()
        
        print(f"\n📊 Indexes created:")
        for idx in indexes:
            print(f"   - {idx[0]}")
        
        cursor.close()
        conn.close()
        
        print("\n✅ All tables and indexes created successfully!")
        return True
        
    except psycopg2.OperationalError as e:
        print(f"❌ Connection failed: {e}")
        return False
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except ImportError:
        print("❌ psycopg2 not installed. Please install it:")
        print("   pip install psycopg2-binary")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = create_tables()
    sys.exit(0 if success else 1)

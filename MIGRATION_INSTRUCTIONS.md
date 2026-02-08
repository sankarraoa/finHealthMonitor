# How to Run the Migration

The migration script `rename_tenant_id_to_organization_id.sql` needs to be executed against your PostgreSQL database.

## Option 1: Using Python Script (Recommended)

1. **Activate your virtual environment:**
   ```bash
   source venv/bin/activate
   ```

2. **Run the migration script:**
   ```bash
   python3 run_migration.py
   ```

This script will automatically use the same database connection as your application (local or Railway based on your `.env` settings).

## Option 2: Using psql Command Line

### If using Local PostgreSQL:

```bash
# Connect to your local database
psql finhealthmonitor

# Then run:
\i rename_tenant_id_to_organization_id.sql
```

Or in one command:
```bash
psql finhealthmonitor -f rename_tenant_id_to_organization_id.sql
```

### If using Railway PostgreSQL:

```bash
# Get your DATABASE_URL from .env or Railway dashboard
# Then run:
psql "postgresql://postgres:password@metro.proxy.rlwy.net:10176/railway" -f rename_tenant_id_to_organization_id.sql
```

Replace the connection string with your actual Railway DATABASE_URL.

## Option 3: Using Python Interactive Shell

```bash
# Activate virtual environment
source venv/bin/activate

# Start Python
python3

# Then run:
>>> from app.database import engine
>>> from sqlalchemy import text
>>> with open('rename_tenant_id_to_organization_id.sql', 'r') as f:
...     sql = f.read()
>>> with engine.connect() as conn:
...     for statement in sql.split(';'):
...         if statement.strip() and not statement.strip().startswith('--'):
...             conn.execute(text(statement))
...             conn.commit()
```

## Verify Migration

After running the migration, verify it worked:

```sql
-- Check tenant_roles table
\d tenant_roles
-- Should show organization_id column (not tenant_id)

-- Check user_tenant_roles table  
\d user_tenant_roles
-- Should show organization_id column (not tenant_id)
```

Or using Python:
```python
from app.database import engine
from sqlalchemy import inspect

inspector = inspect(engine)
columns = [col['name'] for col in inspector.get_columns('tenant_roles')]
print('tenant_roles columns:', columns)
# Should include 'organization_id' and NOT 'tenant_id'
```

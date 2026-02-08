# Database Connection Test Scripts

These scripts test the Railway PostgreSQL connection and create the necessary tables.

## Prerequisites

First, install `psycopg2-binary`:

```bash
# If using venv
source venv/bin/activate
pip install psycopg2-binary

# Or install globally
pip3 install --user psycopg2-binary
```

## Step 1: Test Connection

Run the connection test script:

```bash
python3 scripts/database/test_db_connection.py
```

This will:
- ✅ Test connection to Railway PostgreSQL
- ✅ Display PostgreSQL version
- ✅ List existing tables (if any)

Expected output:
```
🔌 Attempting to connect to Railway PostgreSQL...
✅ Successfully connected to PostgreSQL!
   Version: PostgreSQL 15.x...
   Database: railway

📊 No tables found in database (empty database)

✅ Connection test completed successfully!
```

## Step 2: Run Database Migrations

After confirming the connection works, run the database migrations using Alembic:

```bash
alembic upgrade head
```

This will:
- ✅ Create all necessary tables (including `payroll_risk_analyses`)
- ✅ Create indexes for performance
- ✅ Set up the complete database schema

**Note:** The `create_payroll_tables.py` script has been removed as table creation is now handled by Alembic migrations. Always use `alembic upgrade head` to set up or update your database schema.

## Troubleshooting

### Connection Failed
- Check if Railway PostgreSQL service is running
- Verify the connection string is correct
- Check network connectivity

### Module Not Found
- Make sure `psycopg2-binary` is installed
- Activate your virtual environment if using one

### Permission Errors
- Try running with `python3` instead of `python`
- Make sure you have network access

## Next Steps

After successfully creating the tables:
1. ✅ Connection verified
2. ✅ Tables created
3. Ready for PostgreSQL migration in the code

# Local PostgreSQL Setup Guide

This guide will help you set up a local PostgreSQL database to improve development performance by avoiding slow connections to Railway PostgreSQL.

## Why Use Local PostgreSQL?

- **Faster Performance**: Local database connections are much faster than remote Railway connections
- **Offline Development**: Work without internet connection
- **Better Testing**: Test database operations without affecting production data
- **Cost Savings**: Reduce Railway database usage during development

## Prerequisites

- macOS (this guide is for macOS, but the concept applies to other OS)
- Homebrew installed ([install Homebrew](https://brew.sh) if needed)

## Step 1: Check Railway PostgreSQL Version

First, let's determine what PostgreSQL version Railway is using:

```bash
python3 scripts/database/test_db_connection.py
```

Look for the "Major Version" in the output. Railway typically uses PostgreSQL 15.

## Step 2: Install PostgreSQL Locally

### Option A: Automated Setup (Recommended)

Run the setup script:

```bash
./scripts/database/setup_local_postgres.sh
```

This script will:
- Check your Railway PostgreSQL version
- Install the matching PostgreSQL version via Homebrew
- Start the PostgreSQL service
- Create the `finhealthmonitor` database
- Set up the default user

### Option B: Manual Setup

1. **Install PostgreSQL via Homebrew:**
   ```bash
   # For PostgreSQL 15 (most common on Railway)
   brew install postgresql@15
   
   # Or for PostgreSQL 16
   brew install postgresql@16
   ```

2. **Start PostgreSQL service:**
   ```bash
   brew services start postgresql@15
   # Or: brew services start postgresql@16
   ```

3. **Create database:**
   ```bash
   createdb finhealthmonitor
   ```

4. **Set password (optional):**
   ```bash
   psql finhealthmonitor
   # Then in psql:
   ALTER USER postgres WITH PASSWORD 'postgres';
   \q
   ```

## Step 3: Configure Environment Variables

Create or update your `.env` file:

```bash
# Use local PostgreSQL
USE_LOCAL_DB=true

# Local PostgreSQL connection string
LOCAL_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/finhealthmonitor

# Keep Railway URL for reference (not used when USE_LOCAL_DB=true)
RAILWAY_DATABASE_URL=postgresql://postgres:password@metro.proxy.rlwy.net:10176/railway
```

**Note:** Adjust the `LOCAL_DATABASE_URL` if you:
- Used a different username
- Set a different password
- Created a different database name
- PostgreSQL is running on a different port

## Step 4: Run Database Migrations

Apply the database schema to your local database:

```bash
alembic upgrade head
```

This will create all necessary tables in your local PostgreSQL database.

## Step 5: Verify Setup

Test that the application is using local PostgreSQL:

```bash
python3 -c "from app.config import config; print('Using:', 'Local PostgreSQL' if config.USE_LOCAL_DB else 'Railway PostgreSQL'); print('URL:', config.DATABASE_URL)"
```

You should see:
```
Using: Local PostgreSQL
URL: postgresql://postgres:postgres@localhost:5432/finhealthmonitor
```

## Step 6: Start Your Application

```bash
# Activate virtual environment if using one
source venv/bin/activate

# Start the application
uvicorn app.main:app --reload
```

The application will now use your local PostgreSQL database, which should be significantly faster!

## Switching Between Local and Railway

### Use Local PostgreSQL (Development)
```bash
# In .env file
USE_LOCAL_DB=true
```

### Use Railway PostgreSQL (Production/Testing)
```bash
# In .env file
USE_LOCAL_DB=false
```

Or simply remove the `USE_LOCAL_DB` variable (defaults to Railway).

## Managing Local PostgreSQL

### Start PostgreSQL Service
```bash
brew services start postgresql@15
```

### Stop PostgreSQL Service
```bash
brew services stop postgresql@15
```

### Check PostgreSQL Status
```bash
brew services list | grep postgresql
```

### Connect to Database
```bash
psql finhealthmonitor
# Or with explicit connection
psql -h localhost -U postgres -d finhealthmonitor
```

### View Databases
```bash
psql -l
```

### Drop and Recreate Database (if needed)
```bash
dropdb finhealthmonitor
createdb finhealthmonitor
alembic upgrade head
```

## Troubleshooting

### PostgreSQL Service Won't Start

```bash
# Check if PostgreSQL is already running
brew services list

# Try restarting
brew services restart postgresql@15

# Check logs
tail -f /usr/local/var/log/postgresql@15.log
# Or for newer installations:
tail -f ~/Library/Logs/Homebrew/postgresql@15.log
```

### Connection Refused Error

1. **Check if PostgreSQL is running:**
   ```bash
   brew services list | grep postgresql
   ```

2. **Check PostgreSQL port:**
   ```bash
   lsof -i :5432
   ```

3. **Verify connection string in .env:**
   - Make sure `USE_LOCAL_DB=true`
   - Check `LOCAL_DATABASE_URL` is correct

### Authentication Failed

1. **Reset postgres user password:**
   ```bash
   psql postgres
   ALTER USER postgres WITH PASSWORD 'postgres';
   \q
   ```

2. **Or update LOCAL_DATABASE_URL in .env** with correct credentials

### Database Doesn't Exist

```bash
createdb finhealthmonitor
alembic upgrade head
```

### Version Mismatch

If you installed a different PostgreSQL version than Railway:

1. **Check Railway version:**
   ```bash
   python3 scripts/database/test_db_connection.py
   ```

2. **Uninstall current version:**
   ```bash
   brew services stop postgresql@15
   brew uninstall postgresql@15
   ```

3. **Install correct version:**
   ```bash
   brew install postgresql@<version>
   brew services start postgresql@<version>
   ```

## Performance Comparison

You should notice:
- **Faster page loads**: Database queries execute in milliseconds instead of seconds
- **Quicker development**: No waiting for remote database responses
- **Better debugging**: Can enable SQL query logging without performance impact

## Best Practices

1. **Use local PostgreSQL for development** - Faster and more reliable
2. **Use Railway PostgreSQL for production** - Keep production data separate
3. **Sync schema changes** - Always run migrations on both local and Railway
4. **Backup local data** - Use `pg_dump` to backup your local database
5. **Version matching** - Keep local PostgreSQL version matching Railway for compatibility

## Backup and Restore

### Backup Local Database
```bash
pg_dump finhealthmonitor > finhealthmonitor_backup.sql
```

### Restore Local Database
```bash
psql finhealthmonitor < finhealthmonitor_backup.sql
```

### Export from Railway, Import to Local
```bash
# Export from Railway (requires Railway CLI)
railway connect postgres
pg_dump $DATABASE_URL > railway_backup.sql

# Import to local
psql finhealthmonitor < railway_backup.sql
```

## Next Steps

- ✅ Local PostgreSQL is set up and running
- ✅ Application is configured to use local database
- ✅ Database migrations have been applied
- 🚀 Start developing with faster database performance!

For questions or issues, check the main [README.md](README.md) or Railway deployment guide.

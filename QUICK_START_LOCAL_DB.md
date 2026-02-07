# Quick Start: Local PostgreSQL Setup

## 🚀 Quick Setup (3 Steps)

### 1. Install PostgreSQL
```bash
./setup_local_postgres.sh
```

### 2. Update .env file
Add these lines to your `.env` file:
```bash
USE_LOCAL_DB=true
LOCAL_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/finhealthmonitor
```

### 3. Run migrations
```bash
alembic upgrade head
```

That's it! Your app will now use local PostgreSQL (much faster! 🎉)

## 🔄 Switch Back to Railway

In your `.env` file, change:
```bash
USE_LOCAL_DB=false
```

Or simply remove the `USE_LOCAL_DB` line (defaults to Railway).

## ✅ Verify It's Working

```bash
python3 -c "from app.config import config; print('Using:', 'Local' if config.USE_LOCAL_DB else 'Railway')"
```

Should output: `Using: Local`

## 📚 Full Documentation

See [LOCAL_POSTGRES_SETUP.md](LOCAL_POSTGRES_SETUP.md) for detailed instructions and troubleshooting.

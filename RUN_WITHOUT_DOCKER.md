# Running Microservices Without Docker

You can run the services directly with Python, which is simpler for local development.

## Prerequisites

1. **PostgreSQL must be running locally**
   ```bash
   # Check if PostgreSQL is running
   brew services list | grep postgresql
   
   # If not running, start it
   brew services start postgresql
   
   # Or start manually
   pg_ctl -D /usr/local/var/postgres start
   ```

2. **Create the database** (if it doesn't exist)
   ```bash
   createdb finhealthmonitor
   # Or via psql:
   psql postgres -c "CREATE DATABASE finhealthmonitor;"
   ```

## Step 1: Install Dependencies

```bash
# Make sure you're in the project root
cd /Users/sankar.amburkar/VSCode/finHealthMonitor

# Install dependencies for monolith (gateway)
pip install -r requirements.txt

# Install dependencies for user-service
cd services/user-service
pip install -r requirements.txt
cd ../..
```

## Step 2: Set Up Environment Variables

Create a `.env` file in the project root (or export them):

```bash
# Database (adjust if your PostgreSQL setup is different)
export DATABASE_URL="postgresql://$(whoami)@localhost:5432/finhealthmonitor"
# Or if you have a password:
# export DATABASE_URL="postgresql://postgres:password@localhost:5432/finhealthmonitor"

# JWT Secret (must be the same for both services)
export JWT_SECRET="dev-shared-secret-change-in-production"

# User Service URL (for gateway)
export USER_SERVICE_URL="http://localhost:8001"
```

## Step 3: Run Database Migrations

```bash
# Run migrations for monolith
alembic upgrade head

# Run migrations for user-service
cd services/user-service
alembic upgrade head
cd ../..
```

## Step 4: Start User Service

Open a **new terminal window/tab**:

```bash
cd /Users/sankar.amburkar/VSCode/finHealthMonitor/services/user-service

# Set environment variables
export DATABASE_URL="postgresql://$(whoami)@localhost:5432/finhealthmonitor"
export JWT_SECRET="dev-shared-secret-change-in-production"
export PORT=8001

# Start the service
python -m app.main
```

You should see:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001
```

## Step 5: Start Gateway (Monolith)

Open **another terminal window/tab**:

```bash
cd /Users/sankar.amburkar/VSCode/finHealthMonitor

# Set environment variables
export DATABASE_URL="postgresql://$(whoami)@localhost:5432/finhealthmonitor"
export JWT_SECRET="dev-shared-secret-change-in-production"
export USER_SERVICE_URL="http://localhost:8001"
export PORT=8000

# Start the gateway
python -m app.main
```

You should see:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## Step 6: Test the Services

### Test User Service
```bash
# Health check
curl http://localhost:8001/health

# Should return: {"status":"healthy","service":"user-service","version":"1.0.0"}
```

### Test Gateway
```bash
# Root endpoint
curl http://localhost:8000/

# Should return the gateway response
```

### Test Login (via Gateway)
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "your-email@example.com", "password": "your-password"}'
```

## Using a .env File (Easier)

Instead of exporting variables, create `.env` files:

### Root `.env` (for gateway)
```bash
DATABASE_URL=postgresql://sankar.amburkar@localhost:5432/finhealthmonitor
JWT_SECRET=dev-shared-secret-change-in-production
USER_SERVICE_URL=http://localhost:8001
PORT=8000
```

### `services/user-service/.env`
```bash
DATABASE_URL=postgresql://sankar.amburkar@localhost:5432/finhealthmonitor
JWT_SECRET=dev-shared-secret-change-in-production
PORT=8001
```

Then just run:
```bash
# Terminal 1: User Service
cd services/user-service
python -m app.main

# Terminal 2: Gateway
cd ../..
python -m app.main
```

## Troubleshooting

### PostgreSQL Connection Error
```bash
# Check if PostgreSQL is running
pg_isready

# Check your username
whoami

# Try connecting manually
psql -d finhealthmonitor
```

### Port Already in Use
```bash
# Find what's using port 8000 or 8001
lsof -i :8000
lsof -i :8001

# Kill the process
kill -9 <PID>
```

### Import Errors
Make sure you're in the correct directory and have installed all dependencies:
```bash
pip install -r requirements.txt  # For gateway
cd services/user-service && pip install -r requirements.txt  # For user-service
```

# Microservices Migration Guide

## Overview

This document describes the microservices architecture migration for FinHealthMonitor. We're using the **Strangler Fig Pattern** to gradually extract services from the monolith.

## Current Status

### ✅ Phase 1: User Service (COMPLETED)

The User Management service has been extracted as a standalone microservice.

**Location**: `services/user-service/`

**What was moved:**
- User authentication (login/register)
- User management (CRUD)
- Tenant management
- Role-Based Access Control (RBAC)
- Permission management

**What stayed in monolith:**
- Connections management
- Financial data (accounts, invoices, journals)
- AI/Agents
- UI templates

## Architecture

### Services

1. **Gateway (Monolith)** - Port 8000
   - Serves the web UI
   - Handles connections, financial data, AI agents
   - Proxies user management calls to user-service

2. **User Service** - Port 8001
   - Handles all user/tenant/role/permission operations
   - Issues JWT tokens for authentication
   - Shared database with gateway (for now)

3. **PostgreSQL Database**
   - Shared by all services (Phase 1)
   - Will be split per-service in later phases

### Authentication Flow

1. User logs in via gateway (`POST /api/auth/login`)
2. Gateway calls user-service to authenticate
3. User-service returns JWT token
4. Gateway stores JWT in session (for backward compatibility)
5. Subsequent requests can use either:
   - Session cookie (existing UI)
   - JWT token in `Authorization: Bearer <token>` header (API calls)

## Local Development

### Using Docker Compose (Recommended)

```bash
# Start all services
docker-compose up

# Services will be available at:
# - Gateway: http://localhost:8000
# - User Service: http://localhost:8001
# - PostgreSQL: localhost:5432
```

### Manual Setup

1. **Start PostgreSQL** (if not using Docker)
   ```bash
   # macOS
   brew services start postgresql
   
   # Or use Docker
   docker run -d -p 5432:5432 \
     -e POSTGRES_DB=finhealthmonitor \
     -e POSTGRES_USER=postgres \
     -e POSTGRES_PASSWORD=localdev \
     postgres:16
   ```

2. **Start User Service**
   ```bash
   cd services/user-service
   export DATABASE_URL="postgresql://postgres:localdev@localhost:5432/finhealthmonitor"
   export JWT_SECRET="dev-shared-secret"
   export PORT=8001
   alembic upgrade head
   python -m app.main
   ```

3. **Start Gateway**
   ```bash
   export DATABASE_URL="postgresql://postgres:localdev@localhost:5432/finhealthmonitor"
   export USER_SERVICE_URL="http://localhost:8001"
   export JWT_SECRET="dev-shared-secret"
   export PORT=8000
   alembic upgrade head
   python -m app.main
   ```

## Railway Deployment

### Setup

1. **Create Railway Project**
   - Create a new project in Railway

2. **Add PostgreSQL**
   - Add a PostgreSQL service
   - Railway will set `DATABASE_URL` automatically

3. **Deploy User Service**
   - Create a new service from `services/user-service/`
   - Link to the PostgreSQL service
   - Set environment variable: `JWT_SECRET` (use a strong secret)
   - Railway will auto-detect the Dockerfile and deploy

4. **Deploy Gateway**
   - Create a new service from the root directory
   - Link to the same PostgreSQL service
   - Set environment variables:
     - `USER_SERVICE_URL` - Use Railway's private network URL (e.g., `http://user-service.railway.internal:8001`)
     - `JWT_SECRET` - Must match user-service's JWT_SECRET
   - Railway will auto-detect the Dockerfile and deploy

### Railway Private Networking

Services in the same Railway project can communicate via private networking:
- Format: `http://<service-name>.railway.internal:<port>`
- Example: `http://user-service.railway.internal:8001`
- No egress charges, faster than public URLs

## Environment Variables

### Gateway (Monolith)

```bash
# Database
DATABASE_URL=postgresql://...  # Set by Railway when Postgres is linked
USE_LOCAL_DB=false

# User Service
USER_SERVICE_URL=http://user-service.railway.internal:8001  # Railway private network
# OR for local: http://localhost:8001

# JWT (must match user-service)
JWT_SECRET=your-secret-key-here

# Existing config
XERO_CLIENT_ID=...
XERO_CLIENT_SECRET=...
# etc.
```

### User Service

```bash
# Database
DATABASE_URL=postgresql://...  # Set by Railway when Postgres is linked
USE_LOCAL_DB=false

# JWT (must match gateway)
JWT_SECRET=your-secret-key-here

# Service config
PORT=8001  # Railway sets this automatically
```

## Migration Path

### Phase 1: User Service ✅
- Extract user management
- Add JWT authentication
- Gateway proxies user API calls

### Phase 2: Connections Service (Future)
- Extract connection management (Xero, QuickBooks OAuth)
- Gateway proxies connection API calls

### Phase 3: Financial Data Service (Future)
- Extract accounts, invoices, journals, bank transactions
- Gateway proxies financial data API calls

### Phase 4: AI/Agents Service (Future)
- Extract payroll risk agent, LLM engine
- Gateway proxies AI API calls

## Testing

### Test User Service Directly

```bash
# Login
curl -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password"}'

# Get user (with JWT token)
curl http://localhost:8001/api/tenants/{tenant_id}/users/{user_id} \
  -H "Authorization: Bearer <token>"
```

### Test Gateway Integration

```bash
# Login via gateway (uses user-service)
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password"}'
```

## Troubleshooting

### User Service Not Responding

1. Check if service is running: `curl http://localhost:8001/health`
2. Check logs: `docker-compose logs user-service`
3. Verify database connection: Check `DATABASE_URL` env var

### JWT Token Invalid

1. Ensure `JWT_SECRET` matches between gateway and user-service
2. Check token expiration (default: 24 hours)
3. Verify token format: `Authorization: Bearer <token>`

### Database Connection Issues

1. Verify PostgreSQL is running
2. Check `DATABASE_URL` format
3. Ensure database exists: `psql -U postgres -c "CREATE DATABASE finhealthmonitor;"`

## Next Steps

1. **Monitor Performance**: Watch for latency issues with service calls
2. **Add Caching**: Cache user data in gateway to reduce service calls
3. **Add Circuit Breaker**: Prevent cascade failures
4. **Extract Next Service**: Choose connections or financial data service

## Questions?

See the main README.md or contact the development team.

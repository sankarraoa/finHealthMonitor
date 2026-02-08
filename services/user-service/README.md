# User Service Microservice

This is the User Management microservice for FinHealthMonitor, extracted from the monolith as part of the microservices migration.

## Features

- User authentication (login/register) with JWT tokens
- User management (CRUD operations)
- Tenant management (multi-tenant SaaS support)
- Role-Based Access Control (RBAC)
- Permission management

## API Endpoints

### Authentication
- `POST /api/auth/login` - Login and get JWT token
- `POST /api/auth/register` - Register new user

### Users
- `GET /api/tenants/{tenant_id}/users` - List users in tenant
- `GET /api/tenants/{tenant_id}/users/{user_id}` - Get user details
- `PUT /api/tenants/{tenant_id}/users/{user_id}` - Update user
- `POST /api/tenants/{tenant_id}/users` - Add user to tenant

### Tenants
- `GET /api/tenants` - List all tenants
- `GET /api/tenants/{tenant_id}` - Get tenant details
- `POST /api/tenants` - Create new tenant

### Roles
- `GET /api/tenants/{tenant_id}/roles` - List roles in tenant
- `POST /api/tenants/{tenant_id}/roles` - Create role
- `GET /api/tenants/{tenant_id}/roles/{role_id}/permissions` - Get role permissions

### Permissions
- `GET /api/permissions` - List all permissions
- `GET /api/permissions/by-resource` - List permissions grouped by resource

## Environment Variables

- `DATABASE_URL` - PostgreSQL connection string (Railway sets this automatically)
- `JWT_SECRET` - Secret key for JWT token signing (must match gateway service)
- `PORT` - Port to run on (default: 8001)
- `USE_LOCAL_DB` - Set to "true" to use local database

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql://postgres:localdev@localhost:5432/finhealthmonitor"
export JWT_SECRET="dev-shared-secret"
export PORT=8001

# Run migrations
alembic upgrade head

# Start service
python -m app.main
```

## Docker

```bash
# Build
docker build -t user-service .

# Run
docker run -p 8001:8001 \
  -e DATABASE_URL="postgresql://postgres:localdev@host.docker.internal:5432/finhealthmonitor" \
  -e JWT_SECRET="dev-shared-secret" \
  user-service
```

## Railway Deployment

1. Create a new Railway service
2. Link it to the same PostgreSQL database as the gateway
3. Set environment variables:
   - `JWT_SECRET` (must match gateway)
   - `DATABASE_URL` (automatically set by Railway when Postgres is linked)
4. Deploy

The service will automatically run migrations on startup.

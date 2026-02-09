# Connection Service Microservice

This is the Connection Management microservice for FinHealthMonitor, handling OAuth connections to external services like Xero and QuickBooks.

## Features

- OAuth 2.0 flow management (Xero, QuickBooks)
- Connection CRUD operations
- Token management and refresh
- Multi-tenant support (Xero organizations, QuickBooks companies)
- Connection health checks

## API Endpoints

### Connections
- `GET /api/connections` - List all connections (optionally filtered by tenant_id)
- `GET /api/connections/{connection_id}` - Get a specific connection
- `POST /api/connections` - Create a new connection
- `PUT /api/connections/{connection_id}` - Update a connection
- `DELETE /api/connections/{connection_id}` - Delete a connection

### OAuth
- `GET /api/connections/{connection_id}/connect?software=xero` - Initiate OAuth flow
- `GET /api/connections/{connection_id}/callback?code=...&state=...` - Handle OAuth callback
- `POST /api/connections/{connection_id}/refresh` - Refresh expired access token

### Tenants
- `GET /api/connections/{connection_id}/tenants` - List all tenants for a connection
- `POST /api/connections/{connection_id}/tenants` - Add a tenant to a connection
- `DELETE /api/connections/{connection_id}/tenants/{tenant_id}` - Remove a tenant from a connection

## Environment Variables

- `DATABASE_URL` - PostgreSQL connection string (Railway sets this automatically)
- `PORT` - Port to run on (default: 8002)
- `USE_LOCAL_DB` - Set to "true" to use local database

### Xero OAuth
- `XERO_CLIENT_ID` - Xero OAuth client ID
- `XERO_CLIENT_SECRET` - Xero OAuth client secret
- `XERO_REDIRECT_URI` - Xero OAuth redirect URI (must match Xero app configuration)

### QuickBooks OAuth
- `QUICKBOOKS_CLIENT_ID` - QuickBooks OAuth client ID
- `QUICKBOOKS_CLIENT_SECRET` - QuickBooks OAuth client secret
- `QUICKBOOKS_REDIRECT_URI` - QuickBooks OAuth redirect URI
- `QUICKBOOKS_ENVIRONMENT` - "sandbox" or "production" (default: "production")

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql://postgres:localdev@localhost:5432/finhealthmonitor"
export PORT=8002
export XERO_CLIENT_ID="your_xero_client_id"
export XERO_CLIENT_SECRET="your_xero_client_secret"
export XERO_REDIRECT_URI="http://localhost:8000/callback"

# Run migrations
alembic upgrade head

# Start service
python -m app.main
```

## Docker

```bash
# Build
docker build -t connection-service .

# Run
docker run -p 8002:8002 \
  -e DATABASE_URL="postgresql://postgres:localdev@host.docker.internal:5432/finhealthmonitor" \
  -e XERO_CLIENT_ID="your_client_id" \
  -e XERO_CLIENT_SECRET="your_client_secret" \
  connection-service
```

## Docker Compose

The connection service is included in the root `docker-compose.yml`:

```bash
docker compose up connection-service
```

## Railway Deployment

1. Create a new Railway service from this directory
2. Link a PostgreSQL database
3. Set environment variables (see above)
4. Deploy

The service will automatically run migrations on startup.

## Database Schema

### connections
- `id` (UUID, primary key)
- `tenant_id` (UUID, foreign key to tenants table)
- `category` (string) - finance, hrms, crm
- `software` (string) - xero, quickbooks, etc.
- `name` (string) - User-friendly connection name
- `access_token` (text) - OAuth access token
- `refresh_token` (text) - OAuth refresh token
- `expires_in` (integer) - Token expiration in seconds
- `token_created_at` (ISO string) - When token was created
- `created_at` (ISO string)
- `updated_at` (ISO string)
- `extra_metadata` (JSON) - Additional metadata

### xero_tenants
- `id` (UUID, primary key)
- `connection_id` (UUID, foreign key to connections)
- `tenant_id` (string) - Xero tenant ID or QuickBooks realm ID
- `tenant_name` (string) - Organization/company name
- `xero_connection_id` (string, nullable) - Xero-specific connection ID for disconnecting
- `created_at` (ISO string)

## Architecture

The connection service is a standalone microservice that:
- Manages OAuth flows independently
- Stores connection tokens securely
- Provides REST API for connection management
- Supports multiple tenants per connection (e.g., multiple Xero organizations)

The gateway service proxies connection-related requests to this service.

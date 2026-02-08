# Organization-Based Data Filtering Implementation

## Overview
All database queries are now filtered by `organization_id` from the user's session to ensure data isolation between organizations.

## Session Management
After login, the session contains:
- `user_id` / `person_id` - The authenticated user's ID
- `organization_id` - The organization ID (same as tenant_id)
- `tenant_id` - Alias for organization_id (for backward compatibility)
- `tenant_name` - Organization name

## Key Changes

### 1. Session Storage (`app/auth/session.py`)
- `create_user_session()` now stores `organization_id` explicitly
- `get_current_organization_id()` retrieves organization_id from session
- `logout_user()` clears organization_id

### 2. Dependencies (`app/auth/dependencies.py`)
- `get_current_organization_id_dep()` - Dependency to get organization_id from session
- Use this in routes that need organization filtering

### 3. Connection Manager (`app/connections.py`)
- `get_all_connections(organization_id=None)` - Now filters by organization_id
- `get_connection(connection_id, organization_id=None)` - Verifies connection belongs to organization

### 4. Payroll Risk DB (`app/payroll_risk_db.py`)
- All methods now accept `organization_id` parameter
- `get_all_analyses(organization_id=None, ...)` - Filters analyses by organization
- `get_analysis(analysis_id, organization_id=None)` - Verifies analysis belongs to organization
- `create_analysis(..., organization_id=None)` - Sets organization_id when creating

### 5. Main Routes (`app/main.py`)
- `get_connections_for_selector(organization_id=None)` - Filters connections by organization

## Usage in Routes

### Example 1: Using dependency
```python
from app.auth.dependencies import get_current_organization_id_dep

@app.get("/some-route")
async def some_route(
    request: Request,
    organization_id: str = Depends(get_current_organization_id_dep)
):
    # organization_id is automatically extracted from session
    connections = connection_manager.get_all_connections(organization_id=organization_id)
```

### Example 2: Manual extraction
```python
from app.auth.session import get_current_organization_id

@app.get("/some-route")
async def some_route(request: Request):
    organization_id = get_current_organization_id(request)
    if not organization_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    connections = connection_manager.get_all_connections(organization_id=organization_id)
```

## Tables with organization_id
The following tables have `organization_id` and should be filtered:
- `connections` - OAuth connections
- `payroll_risk_analyses` - Payroll risk analyses
- `mcp_data_cache` - MCP data cache
- `parties` - Base table for organizations and persons
- `permissions` - Global permissions (scoped by organization)
- `user_tenant_roles` - User-role assignments
- `role_permissions` - Role-permission assignments

## Next Steps
1. Update all routes in `app/main.py` to pass `organization_id` to service methods
2. Update MCP cache queries to filter by organization_id
3. Add organization_id filtering to any other data access methods
4. Test that users can only see data from their organization

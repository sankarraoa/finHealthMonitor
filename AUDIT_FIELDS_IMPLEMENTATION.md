# Audit Fields Implementation Guide

## Overview
All create and update operations now automatically set:
- `organization_id` - From the user's session
- `created_by` - Person ID from session (on create)
- `modified_by` - Person ID from session (on update)

## Helper Functions

### Get Session Context
```python
from app.auth.dependencies import get_session_context, get_session_context_dep

# Manual extraction
org_id, person_id = get_session_context(request)

# As a dependency (recommended)
@app.post("/some-route")
async def some_route(
    request: Request,
    org_id, person_id = Depends(get_session_context_dep)
):
    # org_id and person_id are automatically extracted from session
```

## Updated Services

### 1. Connection Manager (`app/connections.py`)
- `add_connection(..., organization_id=None, created_by=None)` - Sets organization_id and created_by
- `update_connection(..., organization_id=None, modified_by=None)` - Sets modified_by on update
- Tenant records also get organization_id, created_by, and modified_by

### 2. Payroll Risk DB (`app/payroll_risk_db.py`)
- `create_analysis(..., organization_id=None, created_by=None)` - Sets organization_id and created_by
- `update_progress(..., organization_id=None, modified_by=None)` - Sets modified_by
- `complete_analysis(..., organization_id=None, modified_by=None)` - Sets modified_by
- `fail_analysis(..., organization_id=None, modified_by=None)` - Sets modified_by

### 3. User Service (`app/services/user_service.py`)
- `create_user(..., organization_id=None, created_by=None)` - Sets organization_id and created_by
- `update_user(..., modified_by=None)` - Sets modified_by

### 4. Tenant Service (`app/services/tenant_service.py`)
- `create_tenant(..., organization_id=None, created_by=None)` - Sets organization_id and created_by
- `update_tenant(..., modified_by=None)` - Sets modified_by

### 5. Role Service (`app/services/role_service.py`)
- `create_role(..., created_by=None)` - Sets created_by
- `update_role(..., modified_by=None)` - Sets modified_by

### 6. Permission Service (`app/services/permission_service.py`)
- `create_permission(..., organization_id=None, created_by=None)` - Sets organization_id and created_by

## Usage in Routes

### Example: Creating a Connection
```python
from app.auth.dependencies import get_session_context_dep

@app.post("/connections")
async def create_connection(
    request: Request,
    connection_data: ConnectionCreate,
    org_id, person_id = Depends(get_session_context_dep)
):
    connection_id = connection_manager.add_connection(
        category=connection_data.category,
        software=connection_data.software,
        name=connection_data.name,
        access_token=connection_data.access_token,
        organization_id=org_id,  # From session
        created_by=person_id      # From session
    )
    return {"connection_id": connection_id}
```

### Example: Updating a User
```python
from app.auth.dependencies import get_session_context_dep

@app.put("/users/{user_id}")
async def update_user(
    request: Request,
    user_id: str,
    user_data: UserUpdate,
    org_id, person_id = Depends(get_session_context_dep)
):
    updated_user = user_service.update_user(
        db,
        user_id=user_id,
        first_name=user_data.first_name,
        modified_by=person_id  # From session
    )
    return updated_user
```

## Notes

1. **On Create**: Both `created_by` and `modified_by` are set to the person_id from session
2. **On Update**: Only `modified_by` is updated (and `modified_at` timestamp)
3. **Organization ID**: Should always be passed from session to ensure data isolation
4. **Backward Compatibility**: All parameters are optional, so existing code continues to work

## Next Steps

Update all routes that create or update records to:
1. Extract `organization_id` and `person_id` from session
2. Pass them to the service methods
3. Use the dependency `get_session_context_dep` for automatic extraction

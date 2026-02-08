# Terminology Refactoring Summary

## Overview
Fixed terminology confusion between "tenant" (Xero/QuickBooks organizations) and "organization" (customer companies).

## Changes Made

### 1. Database Models (`app/models/rbac.py`)
- **TenantRole**: Renamed `tenant_id` → `organization_id`
- **UserTenantRole**: Renamed `tenant_id` → `organization_id`
- Updated relationship names: `tenant` → `organization`
- Updated docstrings to clarify terminology

### 2. Services
- **role_service.py**:
  - `create_role(tenant_id, ...)` → `create_role(organization_id, ...)`
  - `get_role_by_name(tenant_id, ...)` → `get_role_by_name(organization_id, ...)`
  - `list_roles_in_tenant(...)` → `list_roles_in_organization(...)`
  - `create_default_roles_for_tenant(...)` → `create_default_roles_for_organization(...)`

- **user_service.py**:
  - `add_user_to_tenant(...)` → `add_user_to_organization(...)`
  - `remove_user_from_tenant(...)` → `remove_user_from_organization(...)`
  - `get_user_tenants(...)` → `get_user_organizations(...)`
  - `list_users_in_tenant(...)` → `list_users_in_organization(...)`

### 3. API Routes (`app/routes/rbac.py`)
- Updated all route parameters: `tenant_id` → `organization_id` (in RBAC context)
- Updated route function names to reflect organization terminology
- Updated Pydantic models: `TenantCreate` → `OrganizationCreate`, `TenantResponse` → `OrganizationResponse`
- Updated `RoleResponse`: `tenant_id` → `organization_id`
- **Note**: Route paths still use `/tenants/` for backward compatibility

### 4. Relationships (`app/models/party.py`)
- Updated `Organization` relationships: `tenant` → `organization` for RBAC relationships

## Terminology Guidelines

### Use "Organization" for:
- Customer companies (multi-tenant customers)
- The `organizations` table
- RBAC context (roles, user assignments)
- Fields: `organization_id` in RBAC tables

### Use "Tenant" for:
- Xero organizations (stored in `tenants` table)
- QuickBooks companies
- External accounting software organizations
- Fields: `tenant_id`, `tenant_name` in `tenants` table

## Database Migration

A SQL migration script has been created: `rename_tenant_id_to_organization_id.sql`

**To apply the migration:**
```sql
-- Run the migration script
\i rename_tenant_id_to_organization_id.sql
```

This will:
1. Rename `tenant_id` → `organization_id` in `tenant_roles` table
2. Rename `tenant_id` → `organization_id` in `user_tenant_roles` table
3. Update foreign key constraints
4. Update unique constraints
5. Update indexes

**Note**: Table names (`tenant_roles`, `user_tenant_roles`) are kept for backward compatibility.

## Files Not Changed

The following files intentionally keep "tenant" terminology because they refer to Xero/QuickBooks tenants:
- `app/models/connection.py` - `Tenant` model for Xero/QuickBooks
- `app/templates/_tenant_selector.html` - Selector for Xero tenants
- Other files that reference Xero/QuickBooks tenants

## Testing Checklist

After applying the database migration:
- [ ] Verify users can be created and assigned to organizations
- [ ] Verify roles can be created and assigned to organizations
- [ ] Verify permissions can be assigned to roles
- [ ] Verify login works and session contains correct organization_id
- [ ] Verify organization-based data filtering works
- [ ] Verify Xero/QuickBooks tenant functionality still works

## Backward Compatibility

- API route paths still use `/tenants/` (e.g., `/api/tenants/{organization_id}/users`)
- Table names remain `tenant_roles` and `user_tenant_roles`
- Service file remains `tenant_service.py` (can be renamed later if desired)
- Frontend templates continue to work with existing API paths

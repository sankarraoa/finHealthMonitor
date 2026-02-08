-- Complete migration SQL for Railway database
-- This script creates all tables from scratch

BEGIN;

-- Create alembic_version table if it doesn't exist
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Migration 1: b350bf4bd660 - Initial migration
-- Create connections table
CREATE TABLE IF NOT EXISTS connections (
    id VARCHAR NOT NULL, 
    category VARCHAR NOT NULL, 
    software VARCHAR NOT NULL, 
    name VARCHAR NOT NULL, 
    access_token TEXT NOT NULL, 
    refresh_token TEXT, 
    expires_in INTEGER, 
    token_created_at VARCHAR, 
    created_at VARCHAR NOT NULL, 
    updated_at VARCHAR NOT NULL, 
    extra_metadata JSON, 
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_connections_id ON connections (id);
CREATE INDEX IF NOT EXISTS ix_connections_software ON connections (software);

-- Create tenants table (Xero tenants - will be renamed to xero_tenants later)
CREATE TABLE IF NOT EXISTS tenants (
    id VARCHAR NOT NULL, 
    connection_id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    tenant_name VARCHAR NOT NULL, 
    xero_connection_id VARCHAR, 
    created_at VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(connection_id) REFERENCES connections (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_tenants_connection_id ON tenants (connection_id);
CREATE INDEX IF NOT EXISTS ix_tenants_id ON tenants (id);

-- Create payroll_risk_analyses table
CREATE TABLE IF NOT EXISTS payroll_risk_analyses (
    id VARCHAR NOT NULL,
    connection_id VARCHAR NOT NULL,
    connection_name VARCHAR NOT NULL,
    tenant_id VARCHAR,
    tenant_name VARCHAR,
    status VARCHAR NOT NULL,
    initiated_at VARCHAR NOT NULL,
    completed_at VARCHAR,
    result_data TEXT,
    error_message TEXT,
    progress INTEGER DEFAULT 0,
    progress_message TEXT,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_connection_id ON payroll_risk_analyses (connection_id);
CREATE INDEX IF NOT EXISTS idx_status ON payroll_risk_analyses (status);
CREATE INDEX IF NOT EXISTS idx_initiated_at ON payroll_risk_analyses (initiated_at);
CREATE INDEX IF NOT EXISTS ix_payroll_risk_analyses_connection_id ON payroll_risk_analyses (connection_id);
CREATE INDEX IF NOT EXISTS ix_payroll_risk_analyses_id ON payroll_risk_analyses (id);
CREATE INDEX IF NOT EXISTS ix_payroll_risk_analyses_initiated_at ON payroll_risk_analyses (initiated_at);
CREATE INDEX IF NOT EXISTS ix_payroll_risk_analyses_status ON payroll_risk_analyses (status);

-- Migration 2: e83d4d45b357 - Add MCP data cache table
CREATE TABLE IF NOT EXISTS mcp_data_cache (
    id VARCHAR NOT NULL,
    connection_id VARCHAR NOT NULL,
    tenant_id VARCHAR NOT NULL,
    cache_key VARCHAR NOT NULL,
    data TEXT NOT NULL,
    cached_at VARCHAR NOT NULL,
    FOREIGN KEY(connection_id) REFERENCES connections (id) ON DELETE CASCADE,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_cached_at ON mcp_data_cache (cached_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_connection_tenant_key ON mcp_data_cache (connection_id, tenant_id, cache_key);
CREATE INDEX IF NOT EXISTS ix_mcp_data_cache_cache_key ON mcp_data_cache (cache_key);
CREATE INDEX IF NOT EXISTS ix_mcp_data_cache_cached_at ON mcp_data_cache (cached_at);
CREATE INDEX IF NOT EXISTS ix_mcp_data_cache_connection_id ON mcp_data_cache (connection_id);
CREATE INDEX IF NOT EXISTS ix_mcp_data_cache_id ON mcp_data_cache (id);
CREATE INDEX IF NOT EXISTS ix_mcp_data_cache_tenant_id ON mcp_data_cache (tenant_id);

-- Migration 3: c4add9df0df3 - Add multi-tenant RBAC system
-- Rename tenants to xero_tenants
ALTER TABLE tenants RENAME TO xero_tenants;

-- Create parties table
CREATE TABLE IF NOT EXISTS parties (
    id VARCHAR NOT NULL,
    party_type VARCHAR(20) NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at VARCHAR NOT NULL,
    updated_at VARCHAR NOT NULL,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_parties_id ON parties (id);
CREATE INDEX IF NOT EXISTS ix_parties_party_type ON parties (party_type);

-- Create organizations table
CREATE TABLE IF NOT EXISTS organizations (
    id VARCHAR NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    tax_id VARCHAR(50),
    address JSON,
    phone VARCHAR(50),
    email VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT true,
    FOREIGN KEY(id) REFERENCES parties(id) ON DELETE CASCADE,
    PRIMARY KEY (id)
);

-- Create persons table
CREATE TABLE IF NOT EXISTS persons (
    id VARCHAR NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    image_url TEXT,
    password_hash VARCHAR(255),
    phone VARCHAR(50),
    is_active BOOLEAN NOT NULL DEFAULT true,
    FOREIGN KEY(id) REFERENCES parties(id) ON DELETE CASCADE,
    PRIMARY KEY (id),
    UNIQUE (email)
);

CREATE INDEX IF NOT EXISTS ix_persons_email ON persons (email);

-- Create permissions table
CREATE TABLE IF NOT EXISTS permissions (
    id VARCHAR NOT NULL,
    resource VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    description VARCHAR(500),
    created_at VARCHAR NOT NULL,
    updated_at VARCHAR NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (resource, action)
);

CREATE INDEX IF NOT EXISTS ix_permissions_id ON permissions (id);
CREATE INDEX IF NOT EXISTS ix_permissions_resource ON permissions (resource);
CREATE INDEX IF NOT EXISTS ix_permissions_action ON permissions (action);
CREATE INDEX IF NOT EXISTS idx_permission_resource_action ON permissions (resource, action);

-- Create tenant_roles table (note: this references organizations, not tenants)
CREATE TABLE IF NOT EXISTS tenant_roles (
    id VARCHAR NOT NULL,
    tenant_id VARCHAR NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500),
    is_system_role VARCHAR(10) NOT NULL DEFAULT 'false',
    created_at VARCHAR NOT NULL,
    updated_at VARCHAR NOT NULL,
    FOREIGN KEY(tenant_id) REFERENCES organizations(id) ON DELETE CASCADE,
    PRIMARY KEY (id),
    UNIQUE (tenant_id, name)
);

CREATE INDEX IF NOT EXISTS ix_tenant_roles_id ON tenant_roles (id);
CREATE INDEX IF NOT EXISTS ix_tenant_roles_tenant_id ON tenant_roles (tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_role_tenant_name ON tenant_roles (tenant_id, name);

-- Create user_tenant_roles table
CREATE TABLE IF NOT EXISTS user_tenant_roles (
    id VARCHAR NOT NULL,
    user_id VARCHAR NOT NULL,
    tenant_id VARCHAR NOT NULL,
    role_id VARCHAR NOT NULL,
    assigned_at VARCHAR NOT NULL,
    assigned_by VARCHAR,
    FOREIGN KEY(user_id) REFERENCES persons(id) ON DELETE CASCADE,
    FOREIGN KEY(tenant_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY(role_id) REFERENCES tenant_roles(id) ON DELETE CASCADE,
    FOREIGN KEY(assigned_by) REFERENCES persons(id) ON DELETE SET NULL,
    PRIMARY KEY (id),
    UNIQUE (user_id, tenant_id, role_id)
);

CREATE INDEX IF NOT EXISTS ix_user_tenant_roles_id ON user_tenant_roles (id);
CREATE INDEX IF NOT EXISTS ix_user_tenant_roles_user_id ON user_tenant_roles (user_id);
CREATE INDEX IF NOT EXISTS ix_user_tenant_roles_tenant_id ON user_tenant_roles (tenant_id);
CREATE INDEX IF NOT EXISTS ix_user_tenant_roles_role_id ON user_tenant_roles (role_id);
CREATE INDEX IF NOT EXISTS idx_user_tenant_role ON user_tenant_roles (user_id, tenant_id, role_id);

-- Create role_permissions table
CREATE TABLE IF NOT EXISTS role_permissions (
    id VARCHAR NOT NULL,
    role_id VARCHAR NOT NULL,
    permission_id VARCHAR NOT NULL,
    granted_at VARCHAR NOT NULL,
    FOREIGN KEY(role_id) REFERENCES tenant_roles(id) ON DELETE CASCADE,
    FOREIGN KEY(permission_id) REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (id),
    UNIQUE (role_id, permission_id)
);

CREATE INDEX IF NOT EXISTS ix_role_permissions_id ON role_permissions (id);
CREATE INDEX IF NOT EXISTS ix_role_permissions_role_id ON role_permissions (role_id);
CREATE INDEX IF NOT EXISTS ix_role_permissions_permission_id ON role_permissions (permission_id);
CREATE INDEX IF NOT EXISTS idx_role_permission ON role_permissions (role_id, permission_id);

-- Add organization_id to connections table
ALTER TABLE connections ADD COLUMN IF NOT EXISTS organization_id VARCHAR;
CREATE INDEX IF NOT EXISTS ix_connections_organization_id ON connections (organization_id);
-- Note: Foreign key will be added after organizations table is populated if needed

-- Add organization_id to payroll_risk_analyses table
ALTER TABLE payroll_risk_analyses ADD COLUMN IF NOT EXISTS organization_id VARCHAR;
CREATE INDEX IF NOT EXISTS idx_payroll_analyses_organization_id ON payroll_risk_analyses (organization_id);
-- Note: Foreign key will be added after organizations table is populated if needed

-- Add organization_id to mcp_data_cache table
ALTER TABLE mcp_data_cache ADD COLUMN IF NOT EXISTS organization_id VARCHAR;
CREATE INDEX IF NOT EXISTS idx_mcp_cache_organization_id ON mcp_data_cache (organization_id);
-- Note: Foreign key will be added after organizations table is populated if needed

-- Update alembic_version to current revision
DELETE FROM alembic_version;
INSERT INTO alembic_version (version_num) VALUES ('c4add9df0df3');

COMMIT;

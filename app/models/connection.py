"""Connection and Tenant models."""
from sqlalchemy import Column, String, Integer, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

from app.database import Base


class Connection(Base):
    """Model for OAuth connections (Xero, QuickBooks, etc.)."""
    
    __tablename__ = "connections"
    
    id = Column(String, primary_key=True, index=True)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # Multi-tenant organization
    category = Column(String, nullable=False)  # finance, hrms, crm
    software = Column(String, nullable=False, index=True)  # xero, quickbooks, etc.
    name = Column(String, nullable=False)
    access_token = Column(Text, nullable=False)  # Encrypted in production
    refresh_token = Column(Text, nullable=True)  # Encrypted in production
    expires_in = Column(Integer, default=1800)
    token_created_at = Column(String, nullable=True)  # ISO format string
    created_at = Column(String, nullable=False)  # ISO format string
    updated_at = Column(String, nullable=False)  # ISO format string
    extra_metadata = Column(JSON, nullable=True, default=dict)  # Additional metadata as JSON (renamed from 'metadata' to avoid SQLAlchemy conflict)
    
    # Relationships
    tenant = relationship("Organization", foreign_keys=[organization_id], back_populates="connections")
    tenants = relationship("Tenant", back_populates="connection", cascade="all, delete-orphan")  # Xero/QuickBooks tenants
    
    def __repr__(self):
        return f"<Connection(id={self.id}, software={self.software}, name={self.name})>"


class Tenant(Base):
    """Model for tenants/organizations within a connection (e.g., Xero organizations)."""
    
    __tablename__ = "tenants"
    
    id = Column(String, primary_key=True, index=True)  # UUID
    connection_id = Column(String, ForeignKey("connections.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(String, nullable=False)  # Xero tenant_id, QuickBooks realm_id, etc.
    tenant_name = Column(String, nullable=False)
    xero_connection_id = Column(String, nullable=True)  # Xero-specific connection ID
    created_at = Column(String, nullable=False)  # ISO format string
    
    # Relationship back to connection
    connection = relationship("Connection", back_populates="tenants")
    
    def __repr__(self):
        return f"<Tenant(id={self.id}, tenant_id={self.tenant_id}, name={self.tenant_name})>"

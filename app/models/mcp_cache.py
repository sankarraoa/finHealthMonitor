"""MCP Data Cache model."""
from sqlalchemy import Column, String, Text, DateTime, Index, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import json

from app.database import Base


class MCPDataCache(Base):
    """Model for caching MCP (Xero/QuickBooks) data per connection and tenant."""
    
    __tablename__ = "mcp_data_cache"
    
    id = Column(String, primary_key=True, index=True)  # UUID
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)  # Multi-tenant tenant (B2B SaaS)
    connection_id = Column(String, ForeignKey("connections.id", ondelete="CASCADE"), nullable=False, index=True)
    xero_tenant_id = Column(String, nullable=False, index=True)  # Xero tenant_id, QuickBooks realm_id, etc.
    cache_key = Column(String, nullable=False, index=True)  # e.g., "organisation", "accounts", "invoices"
    data = Column(Text, nullable=False)  # JSON data stored as text
    cached_at = Column(String, nullable=False, index=True)  # ISO format timestamp
    
    # Relationships
    tenant = relationship("Tenant", foreign_keys=[tenant_id], back_populates=None)  # Optional relationship
    
    # Composite index for fast lookups
    __table_args__ = (
        Index('idx_connection_xero_tenant_key', 'connection_id', 'xero_tenant_id', 'cache_key', unique=True),
        Index('idx_cached_at', 'cached_at'),
        Index('idx_mcp_cache_tenant_id', 'tenant_id'),
    )
    
    def __repr__(self):
        return f"<MCPDataCache(id={self.id}, connection_id={self.connection_id}, xero_tenant_id={self.xero_tenant_id}, cache_key={self.cache_key})>"
    
    def get_data_dict(self) -> dict:
        """Parse JSON data and return as dict."""
        try:
            return json.loads(self.data)
        except json.JSONDecodeError:
            return {}

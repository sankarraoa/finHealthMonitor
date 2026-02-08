"""Payroll Risk Analysis model."""
from sqlalchemy import Column, String, Integer, Text, Index, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class PayrollRiskAnalysis(Base):
    """Model for payroll risk analyses."""
    
    __tablename__ = "payroll_risk_analyses"
    
    id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)  # Multi-tenant tenant (B2B SaaS)
    connection_id = Column(String, nullable=False, index=True)
    connection_name = Column(String, nullable=False)
    xero_tenant_id = Column(String, nullable=True)  # Xero/QuickBooks tenant_id
    xero_tenant_name = Column(String, nullable=True)  # Xero/QuickBooks tenant_name
    status = Column(String, nullable=False, index=True)  # running, completed, failed
    initiated_at = Column(String, nullable=False, index=True)
    completed_at = Column(String, nullable=True)
    result_data = Column(Text, nullable=True)  # JSON stored as text
    error_message = Column(Text, nullable=True)
    progress = Column(Integer, default=0)
    progress_message = Column(Text, nullable=True)
    
    # Relationships
    tenant = relationship("Tenant", foreign_keys=[tenant_id], back_populates="payroll_analyses")
    
    # Indexes (already created in PostgreSQL, but defined here for Alembic)
    __table_args__ = (
        Index('idx_connection_id', 'connection_id'),
        Index('idx_status', 'status'),
        Index('idx_initiated_at', 'initiated_at'),
        Index('idx_payroll_analyses_tenant_id', 'tenant_id'),
    )
    
    def __repr__(self):
        return f"<PayrollRiskAnalysis(id={self.id}, status={self.status}, connection_id={self.connection_id})>"

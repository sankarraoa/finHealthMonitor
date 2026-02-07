"""Payroll Risk Analysis model."""
from sqlalchemy import Column, String, Integer, Text, Index, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class PayrollRiskAnalysis(Base):
    """Model for payroll risk analyses."""
    
    __tablename__ = "payroll_risk_analyses"
    
    id = Column(String, primary_key=True, index=True)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)  # Multi-tenant organization
    connection_id = Column(String, nullable=False, index=True)
    connection_name = Column(String, nullable=False)
    tenant_id = Column(String, nullable=True)  # Xero/QuickBooks tenant_id
    tenant_name = Column(String, nullable=True)  # Xero/QuickBooks tenant_name
    status = Column(String, nullable=False, index=True)  # running, completed, failed
    initiated_at = Column(String, nullable=False, index=True)
    completed_at = Column(String, nullable=True)
    result_data = Column(Text, nullable=True)  # JSON stored as text
    error_message = Column(Text, nullable=True)
    progress = Column(Integer, default=0)
    progress_message = Column(Text, nullable=True)
    
    # Relationships
    tenant = relationship("Organization", foreign_keys=[organization_id], back_populates="payroll_analyses")
    
    # Indexes (already created in PostgreSQL, but defined here for Alembic)
    __table_args__ = (
        Index('idx_connection_id', 'connection_id'),
        Index('idx_status', 'status'),
        Index('idx_initiated_at', 'initiated_at'),
        Index('idx_payroll_analyses_organization_id', 'organization_id'),
    )
    
    def __repr__(self):
        return f"<PayrollRiskAnalysis(id={self.id}, status={self.status}, connection_id={self.connection_id})>"

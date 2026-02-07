"""Party model system - Organizations and Persons."""
from sqlalchemy import Column, String, Text, Boolean, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declared_attr
from datetime import datetime
import uuid

from app.database import Base


class Party(Base):
    """Abstract base class for Organizations and Persons (Party pattern)."""
    
    __tablename__ = "parties"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    party_type = Column(String(20), nullable=False, index=True)  # 'organization' or 'person'
    name = Column(String(255), nullable=False)
    created_at = Column(String, nullable=False, default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String, nullable=False, default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())
    
    __mapper_args__ = {
        'polymorphic_identity': 'party',
        'polymorphic_on': party_type
    }
    
    def __repr__(self):
        return f"<Party(id={self.id}, type={self.party_type}, name={self.name})>"


class Organization(Party):
    """Organization model - represents tenant/customer companies."""
    
    __tablename__ = "organizations"
    
    id = Column(String, ForeignKey("parties.id", ondelete="CASCADE"), primary_key=True)
    company_name = Column(String(255), nullable=False)
    tax_id = Column(String(50), nullable=True)
    address = Column(JSON, nullable=True)  # JSON field for address details
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    users = relationship("UserTenantRole", back_populates="tenant", cascade="all, delete-orphan")
    connections = relationship("Connection", back_populates="tenant", cascade="all, delete-orphan")
    payroll_analyses = relationship("PayrollRiskAnalysis", back_populates="tenant", cascade="all, delete-orphan")
    tenant_roles = relationship("TenantRole", back_populates="tenant", cascade="all, delete-orphan")
    
    __mapper_args__ = {
        'polymorphic_identity': 'organization',
        'inherit_condition': (id == Party.id),
    }
    
    def __repr__(self):
        return f"<Organization(id={self.id}, name={self.company_name})>"


class Person(Party):
    """Person model - represents users/individuals."""
    
    __tablename__ = "persons"
    
    id = Column(String, ForeignKey("parties.id", ondelete="CASCADE"), primary_key=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    image_url = Column(Text, nullable=True)
    password_hash = Column(String(255), nullable=True)  # Nullable for OAuth-only users
    phone = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    tenant_memberships = relationship(
        "UserTenantRole", 
        foreign_keys="UserTenantRole.user_id",
        back_populates="user", 
        cascade="all, delete-orphan",
        primaryjoin="Person.id == UserTenantRole.user_id"
    )
    
    __mapper_args__ = {
        'polymorphic_identity': 'person',
        'inherit_condition': (id == Party.id),
    }
    
    @property
    def full_name(self):
        """Return full name."""
        return f"{self.first_name} {self.last_name}"
    
    def __repr__(self):
        return f"<Person(id={self.id}, email={self.email}, name={self.full_name})>"

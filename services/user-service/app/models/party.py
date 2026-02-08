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
    # These columns exist in parties table
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    created_by = Column(String, ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)
    modified_by = Column(String, ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)
    
    __mapper_args__ = {
        'polymorphic_identity': 'party',
        'polymorphic_on': party_type
    }
    
    def __repr__(self):
        return f"<Party(id={self.id}, type={self.party_type}, name={self.name})>"

class Tenant(Party):
    """Tenant model - represents customer companies (B2B SaaS tenants)."""
    
    __tablename__ = "tenants"
    
    id = Column(String, ForeignKey("parties.id", ondelete="CASCADE"), primary_key=True)
    company_name = Column(String(255), nullable=False)
    tax_id = Column(String(50), nullable=True)
    address = Column(JSON, nullable=True)  # JSON field for address details
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    # Note: tenant_id, created_by, modified_by are inherited from Party (parties table)
    
    # Relationships - only include relationships to models in this service
    users = relationship("UserTenantRole", back_populates="tenant", cascade="all, delete-orphan")
    tenant_roles = relationship("TenantRole", back_populates="tenant", cascade="all, delete-orphan")
    # Note: connections and payroll_analyses relationships are in other services
    
    __mapper_args__ = {
        'polymorphic_identity': 'organization',
        'inherit_condition': (id == Party.id),
        'exclude_properties': []
    }
    
    def __repr__(self):
        return f"<Tenant(id={self.id}, name={self.company_name})>"

class Organization(Base):
    """Organization model - represents organization entities (e.g., vendors, suppliers).
    
    This is a separate table from tenants. For every record in parties with 
    party_type='organization', there should be a corresponding record in this table.
    
    The tenant_id field points to the B2B SaaS tenant (customer) that this organization
    belongs to. For example, if OpenAI is a tenant and NVidia is a vendor organization,
    then NVidia's organization record will have tenant_id pointing to OpenAI.
    """
    
    __tablename__ = "organizations"
    
    id = Column(String, ForeignKey("parties.id", ondelete="CASCADE"), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    created_by = Column(String, ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)
    modified_by = Column(String, ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)
    
    # Relationships
    party = relationship("Party", foreign_keys=[id], backref="organization")
    tenant = relationship("Tenant", foreign_keys=[tenant_id], backref="organizations")
    creator = relationship("Person", foreign_keys=[created_by], post_update=True)
    modifier = relationship("Person", foreign_keys=[modified_by], post_update=True)
    
    def __repr__(self):
        return f"<Organization(id={self.id}, name={self.name}, tenant_id={self.tenant_id})>"

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
    # These columns exist in both parties table (inherited from Party) AND persons table (separate columns)
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    created_by = Column(String, ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)
    modified_by = Column(String, ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)
    # Person also has created_at and modified_at (in persons table) - separate from Party's created_at/updated_at
    created_at = Column(String, nullable=True)  # Timestamp when person record was created (in persons table)
    modified_at = Column(String, nullable=True)  # Timestamp when person record was last modified (in persons table)
    
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
        'exclude_properties': []
    }
    
    @property
    def full_name(self):
        """Return full name."""
        return f"{self.first_name} {self.last_name}"
    
    def __repr__(self):
        return f"<Person(id={self.id}, email={self.email}, name={self.full_name})>"

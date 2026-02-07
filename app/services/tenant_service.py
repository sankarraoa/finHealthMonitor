"""Service for tenant (Organization) management."""
from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.party import Organization
import uuid
from datetime import datetime


def create_tenant(
    db: Session,
    company_name: str,
    tax_id: Optional[str] = None,
    address: Optional[dict] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None
) -> Organization:
    """Create a new tenant organization."""
    from app.models.party import Party
    
    now = datetime.utcnow().isoformat()
    tenant_id = str(uuid.uuid4())
    
    # Create Organization - SQLAlchemy will automatically create Party record due to inheritance
    tenant = Organization(
        id=tenant_id,
        company_name=company_name,
        tax_id=tax_id,
        address=address,
        phone=phone,
        email=email,
        is_active=True
    )
    # Set inherited Party attributes
    tenant.party_type = 'organization'
    tenant.name = company_name
    tenant.created_at = now
    tenant.updated_at = now
    
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def get_tenant_by_id(db: Session, tenant_id: str) -> Optional[Organization]:
    """Get tenant by ID."""
    return db.query(Organization).filter(Organization.id == tenant_id).first()


def get_tenant_by_name(db: Session, company_name: str) -> Optional[Organization]:
    """Get tenant by company name."""
    return db.query(Organization).filter(Organization.company_name == company_name).first()


def list_tenants(db: Session, skip: int = 0, limit: int = 100) -> List[Organization]:
    """List all active tenants."""
    return db.query(Organization).filter(Organization.is_active == True).offset(skip).limit(limit).all()


def update_tenant(
    db: Session,
    tenant_id: str,
    company_name: Optional[str] = None,
    tax_id: Optional[str] = None,
    address: Optional[dict] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    is_active: Optional[bool] = None
) -> Optional[Organization]:
    """Update tenant information."""
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        return None
    
    if company_name is not None:
        tenant.company_name = company_name
        tenant.name = company_name
    if tax_id is not None:
        tenant.tax_id = tax_id
    if address is not None:
        tenant.address = address
    if phone is not None:
        tenant.phone = phone
    if email is not None:
        tenant.email = email
    if is_active is not None:
        tenant.is_active = is_active
    
    tenant.updated_at = datetime.utcnow().isoformat()
    db.commit()
    db.refresh(tenant)
    return tenant


def deactivate_tenant(db: Session, tenant_id: str) -> bool:
    """Deactivate a tenant."""
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        return False
    
    tenant.is_active = False
    tenant.updated_at = datetime.utcnow().isoformat()
    db.commit()
    return True

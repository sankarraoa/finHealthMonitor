"""Service for tenant management."""
from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.party import Tenant
import uuid
from datetime import datetime


def create_tenant(
    db: Session,
    company_name: str,
    tax_id: Optional[str] = None,
    address: Optional[dict] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    parent_tenant_id: Optional[str] = None,
    created_by: Optional[str] = None
) -> Tenant:
    """Create a new tenant."""
    from app.models.party import Party
    
    now = datetime.utcnow().isoformat()
    tenant_id = str(uuid.uuid4())
    
    # Create Tenant - SQLAlchemy will automatically create Party record due to inheritance
    tenant = Tenant(
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
    tenant.tenant_id = parent_tenant_id
    tenant.created_by = created_by
    tenant.modified_by = created_by  # Set modified_by to created_by on creation
    
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def get_tenant_by_id(db: Session, tenant_id: str) -> Optional[Tenant]:
    """Get tenant by ID."""
    return db.query(Tenant).filter(Tenant.id == tenant_id).first()


def get_tenant_by_name(db: Session, company_name: str) -> Optional[Tenant]:
    """Get tenant by company name."""
    return db.query(Tenant).filter(Tenant.company_name == company_name).first()


def list_tenants(db: Session, skip: int = 0, limit: int = 100) -> List[Tenant]:
    """List all active tenants."""
    return db.query(Tenant).filter(Tenant.is_active == True).offset(skip).limit(limit).all()


def update_tenant(
    db: Session,
    tenant_id: str,
    company_name: Optional[str] = None,
    tax_id: Optional[str] = None,
    address: Optional[dict] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    is_active: Optional[bool] = None,
    modified_by: Optional[str] = None
) -> Optional[Tenant]:
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
    if modified_by:
        tenant.modified_by = modified_by
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

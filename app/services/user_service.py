"""Service for user (Person) management."""
from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.party import Person, Tenant
from app.models.rbac import UserTenantRole, TenantRole
from app.auth.password import hash_password, verify_password
import uuid
from datetime import datetime


def create_user(
    db: Session,
    email: str,
    first_name: str,
    last_name: str,
    password: Optional[str] = None,
    phone: Optional[str] = None,
    image_url: Optional[str] = None,
    tenant_id: Optional[str] = None,
    created_by: Optional[str] = None
) -> Person:
    """Create a new user."""
    from app.models.party import Party
    
    now = datetime.utcnow().isoformat()
    user_id = str(uuid.uuid4())
    full_name = f"{first_name} {last_name}"
    
    # Hash password before creating objects (do this first to avoid issues)
    password_hash = None
    if password:
        password_hash = hash_password(password)
    
    # Create Person - SQLAlchemy will automatically create Party record due to inheritance
    # We need to set the Party attributes through the Person object
    user = Person(
        id=user_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=password_hash,
        phone=phone,
        image_url=image_url,
        is_active=True
    )
    # Set inherited Party attributes (these go to the parties table)
    user.party_type = 'person'
    user.name = full_name
    
    # Set timestamps and audit fields - with joined-table inheritance:
    # - Party has tenant_id, created_by, modified_by, created_at, updated_at (in parties table)  
    # - Person has tenant_id, created_by, modified_by, created_at, modified_at (in persons table)
    # Since Person's columns shadow Party's, we need to set them via the mapper
    
    from sqlalchemy.orm import object_mapper
    from sqlalchemy import inspect as sa_inspect
    
    mapper = object_mapper(user)
    state = sa_inspect(user)
    
    # Set Party's fields (parties table) - organization_id, created_by, modified_by, created_at, updated_at
    for table in mapper.tables:
        if table.name == 'parties':
            # Set Party's tenant_id
            if 'tenant_id' in table.c:
                state.dict[table.c.tenant_id.key] = tenant_id
            # Set Party's created_by
            if 'created_by' in table.c:
                state.dict[table.c.created_by.key] = created_by
            # Set Party's modified_by
            if 'modified_by' in table.c:
                state.dict[table.c.modified_by.key] = created_by if created_by else None
            # Set Party's created_at
            if 'created_at' in table.c:
                state.dict[table.c.created_at.key] = now
            # Set Party's updated_at
            if 'updated_at' in table.c:
                state.dict[table.c.updated_at.key] = now
            break
    
    # Set Person's fields (persons table) - organization_id, created_by, modified_by, created_at, modified_at
    for table in mapper.tables:
        if table.name == 'persons':
            # Set Person's tenant_id
            if 'tenant_id' in table.c:
                state.dict[table.c.tenant_id.key] = tenant_id
            # Set Person's created_by
            if 'created_by' in table.c:
                state.dict[table.c.created_by.key] = created_by
            # Set Person's modified_by
            if 'modified_by' in table.c:
                state.dict[table.c.modified_by.key] = created_by if created_by else None
            # Set Person's created_at
            if 'created_at' in table.c:
                state.dict[table.c.created_at.key] = now
            # Set Person's modified_at
            if 'modified_at' in table.c:
                state.dict[table.c.modified_at.key] = now
            break
    
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_id(db: Session, user_id: str) -> Optional[Person]:
    """Get user by ID."""
    return db.query(Person).filter(Person.id == user_id).first()


def get_user_by_email(db: Session, email: str) -> Optional[Person]:
    """Get user by email."""
    return db.query(Person).filter(Person.email == email).first()


def authenticate_user(db: Session, email: str, password: str) -> Optional[Person]:
    """Authenticate user with email and password."""
    user = get_user_by_email(db, email)
    if not user or not user.is_active:
        return None
    
    if not user.password_hash:
        return None  # User doesn't have password set
    
    if verify_password(password, user.password_hash):
        return user
    
    return None


def update_user(
    db: Session,
    user_id: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    phone: Optional[str] = None,
    image_url: Optional[str] = None,
    password: Optional[str] = None,
    modified_by: Optional[str] = None
) -> Optional[Person]:
    """Update user information."""
    user = get_user_by_id(db, user_id)
    if not user:
        return None
    
    if first_name is not None:
        user.first_name = first_name
        user.name = f"{first_name} {user.last_name}"
    if last_name is not None:
        user.last_name = last_name
        user.name = f"{user.first_name} {last_name}"
    if phone is not None:
        user.phone = phone
    if image_url is not None:
        user.image_url = image_url
    if password is not None:
        user.password_hash = hash_password(password)
    
    user.updated_at = datetime.utcnow().isoformat()  # Update parties.updated_at
    if modified_by:
        user.modified_by = modified_by
    # Update persons.modified_at
    user.modified_at = datetime.utcnow().isoformat()
    db.commit()
    db.refresh(user)
    return user


def add_user_to_tenant(
    db: Session,
    user_id: str,
    tenant_id: str,
    role_id: str,
    assigned_by: Optional[str] = None
) -> UserTenantRole:
    """Add user to tenant with a role."""
    now = datetime.utcnow().isoformat()
    
    membership = UserTenantRole(
        id=str(uuid.uuid4()),
        user_id=user_id,
        tenant_id=tenant_id,
        role_id=role_id,
        assigned_at=now,
        assigned_by=assigned_by
    )
    
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


def remove_user_from_tenant(db: Session, user_id: str, tenant_id: str) -> bool:
    """Remove user from tenant (removes all role assignments)."""
    memberships = db.query(UserTenantRole).filter(
        UserTenantRole.user_id == user_id,
        UserTenantRole.tenant_id == tenant_id
    ).all()
    
    for membership in memberships:
        db.delete(membership)
    
    db.commit()
    return True


def get_user_tenants(db: Session, user_id: str) -> List[Tenant]:
    """Get all tenants a user belongs to."""
    memberships = db.query(UserTenantRole).filter(
        UserTenantRole.user_id == user_id
    ).all()
    
    tenant_ids = [m.tenant_id for m in memberships]
    return db.query(Tenant).filter(Tenant.id.in_(tenant_ids)).all()


def list_users_in_tenant(db: Session, tenant_id: str, skip: int = 0, limit: int = 100) -> List[Person]:
    """List all users in a tenant."""
    memberships = db.query(UserTenantRole).filter(
        UserTenantRole.tenant_id == tenant_id
    ).offset(skip).limit(limit).all()
    
    user_ids = [m.user_id for m in memberships]
    return db.query(Person).filter(Person.id.in_(user_ids)).all()

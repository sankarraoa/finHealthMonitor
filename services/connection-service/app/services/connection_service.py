"""Connection management service."""
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models.connection import Connection, XeroTenant

logger = logging.getLogger(__name__)


class ConnectionService:
    """Manages OAuth connections (Xero, QuickBooks, etc.)."""
    
    SOFTWARE_CATEGORIES = {
        "finance": {
            "name": "Finance Software",
            "software": {
                "xero": {"name": "Xero", "icon": "🏦"},
                "quickbooks": {"name": "QuickBooks", "icon": "📊"}
            }
        },
        "hrms": {
            "name": "HRMS",
            "software": {
                "bamboohr": {"name": "BambooHR", "icon": "👥"},
                "workday": {"name": "Workday", "icon": "💼"}
            }
        },
        "crm": {
            "name": "CRM",
            "software": {
                "salesforce": {"name": "Salesforce", "icon": "☁️"},
                "hubspot": {"name": "HubSpot", "icon": "🎯"}
            }
        }
    }
    
    def _get_db(self) -> Session:
        """Get database session."""
        return SessionLocal()
    
    def _connection_to_dict(self, conn: Connection) -> Dict[str, Any]:
        """Convert Connection model to dict format."""
        tenants_list = []
        for tenant in conn.xero_tenants:
            tenants_list.append({
                "tenant_id": tenant.tenant_id,
                "tenant_name": tenant.tenant_name,
                "xero_connection_id": tenant.xero_connection_id
            })
        
        return {
            "id": conn.id,
            "tenant_id": conn.tenant_id,
            "category": conn.category,
            "software": conn.software,
            "name": conn.name,
            "access_token": conn.access_token,
            "refresh_token": conn.refresh_token,
            "expires_in": conn.expires_in,
            "token_created_at": conn.token_created_at,
            "created_at": conn.created_at,
            "updated_at": conn.updated_at,
            "metadata": conn.extra_metadata or {},
            "tenants": tenants_list
        }
    
    def get_all_connections(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all connections, optionally filtered by tenant_id."""
        db = self._get_db()
        try:
            query = db.query(Connection).options(joinedload(Connection.xero_tenants))
            if tenant_id:
                query = query.filter(Connection.tenant_id == tenant_id)
            connections = query.all()
            return [self._connection_to_dict(conn) for conn in connections]
        except SQLAlchemyError as e:
            logger.error(f"Error getting all connections: {str(e)}")
            return []
        finally:
            db.close()
    
    def get_connection(self, connection_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a specific connection by ID."""
        db = self._get_db()
        try:
            query = db.query(Connection).options(joinedload(Connection.xero_tenants)).filter(Connection.id == connection_id)
            if tenant_id:
                query = query.filter(Connection.tenant_id == tenant_id)
            conn = query.first()
            return self._connection_to_dict(conn) if conn else None
        except SQLAlchemyError as e:
            logger.error(f"Error getting connection: {str(e)}")
            return None
        finally:
            db.close()
    
    def create_connection(
        self,
        category: str,
        software: str,
        name: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        tenant_id: Optional[str] = None,
        expires_in: int = 1800,
        metadata: Optional[Dict[str, Any]] = None,
        tenants: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Create a new connection."""
        db = self._get_db()
        connection_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        try:
            conn = Connection(
                id=connection_id,
                tenant_id=tenant_id,
                category=category,
                software=software,
                name=name,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=expires_in,
                token_created_at=now,
                created_at=now,
                updated_at=now,
                extra_metadata=metadata or {}
            )
            db.add(conn)
            db.flush()
            
            if tenants:
                for tenant_data in tenants:
                    tenant = XeroTenant(
                        id=str(uuid.uuid4()),
                        connection_id=connection_id,
                        tenant_id=tenant_data.get("tenant_id"),
                        tenant_name=tenant_data.get("tenant_name", ""),
                        xero_connection_id=tenant_data.get("xero_connection_id"),
                        created_at=now
                    )
                    db.add(tenant)
            
            db.commit()
            logger.info(f"Created connection: {name} ({software})")
            return connection_id
        except SQLAlchemyError as e:
            logger.error(f"Error creating connection: {str(e)}")
            db.rollback()
            raise
        finally:
            db.close()
    
    def update_connection(
        self,
        connection_id: str,
        name: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        expires_in: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tenants: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Update an existing connection."""
        db = self._get_db()
        try:
            conn = db.query(Connection).filter(Connection.id == connection_id).first()
            if not conn:
                return False
            
            if name is not None:
                conn.name = name
            if access_token is not None:
                conn.access_token = access_token
            if refresh_token is not None:
                conn.refresh_token = refresh_token
            if expires_in is not None:
                conn.expires_in = expires_in
                conn.token_created_at = datetime.now().isoformat()
            if metadata is not None:
                existing_metadata = conn.extra_metadata or {}
                existing_metadata.update(metadata)
                conn.extra_metadata = existing_metadata
            
            if tenants is not None:
                # Replace all tenants
                db.query(XeroTenant).filter(XeroTenant.connection_id == connection_id).delete()
                now = datetime.now().isoformat()
                for tenant_data in tenants:
                    tenant = XeroTenant(
                        id=str(uuid.uuid4()),
                        connection_id=connection_id,
                        tenant_id=tenant_data.get("tenant_id"),
                        tenant_name=tenant_data.get("tenant_name", ""),
                        xero_connection_id=tenant_data.get("xero_connection_id"),
                        created_at=now
                    )
                    db.add(tenant)
            
            conn.updated_at = datetime.now().isoformat()
            db.commit()
            logger.info(f"Updated connection: {connection_id}")
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error updating connection: {str(e)}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def delete_connection(self, connection_id: str) -> bool:
        """Delete a connection (cascade deletes tenants)."""
        db = self._get_db()
        try:
            conn = db.query(Connection).filter(Connection.id == connection_id).first()
            if not conn:
                return False
            db.delete(conn)
            db.commit()
            logger.info(f"Deleted connection: {connection_id}")
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error deleting connection: {str(e)}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def is_token_expired(self, connection_id: str) -> bool:
        """Check if a connection's token is expired."""
        conn = self.get_connection(connection_id)
        if not conn:
            return True
        
        token_created_at = conn.get("token_created_at")
        expires_in = conn.get("expires_in", 1800)
        
        if not token_created_at:
            return True
        
        try:
            created_time = datetime.fromisoformat(token_created_at)
            expiry_time = created_time + timedelta(seconds=expires_in)
            return datetime.now() >= expiry_time
        except Exception:
            return True
    
    def add_tenant(self, connection_id: str, tenant_id: str, tenant_name: str, xero_connection_id: Optional[str] = None) -> bool:
        """Add a tenant to an existing connection."""
        db = self._get_db()
        try:
            conn = db.query(Connection).filter(Connection.id == connection_id).first()
            if not conn:
                return False
            
            # Check if tenant already exists
            existing = db.query(XeroTenant).filter(
                XeroTenant.connection_id == connection_id,
                XeroTenant.tenant_id == tenant_id
            ).first()
            
            if existing:
                return False
            
            tenant = XeroTenant(
                id=str(uuid.uuid4()),
                connection_id=connection_id,
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                xero_connection_id=xero_connection_id,
                created_at=datetime.now().isoformat()
            )
            db.add(tenant)
            conn.updated_at = datetime.now().isoformat()
            db.commit()
            logger.info(f"Added tenant {tenant_name} to connection {connection_id}")
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error adding tenant: {str(e)}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def remove_tenant(self, connection_id: str, tenant_id: str) -> bool:
        """Remove a tenant from a connection."""
        db = self._get_db()
        try:
            tenant = db.query(XeroTenant).filter(
                XeroTenant.connection_id == connection_id,
                XeroTenant.tenant_id == tenant_id
            ).first()
            
            if not tenant:
                return False
            
            conn = db.query(Connection).filter(Connection.id == connection_id).first()
            if conn:
                conn.updated_at = datetime.now().isoformat()
            
            db.delete(tenant)
            db.commit()
            logger.info(f"Removed tenant {tenant_id} from connection {connection_id}")
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error removing tenant: {str(e)}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def get_all_tenants_for_connection(self, connection_id: str) -> List[Dict[str, Any]]:
        """Get all tenants for a connection."""
        db = self._get_db()
        try:
            conn = db.query(Connection).options(joinedload(Connection.xero_tenants)).filter(Connection.id == connection_id).first()
            if not conn:
                return []
            
            return [
                {
                    "tenant_id": tenant.tenant_id,
                    "tenant_name": tenant.tenant_name,
                    "xero_connection_id": tenant.xero_connection_id
                }
                for tenant in conn.xero_tenants
            ]
        except SQLAlchemyError as e:
            logger.error(f"Error getting tenants for connection: {str(e)}")
            return []
        finally:
            db.close()

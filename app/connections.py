"""Connection management for multiple integrations using SQLAlchemy."""
import json
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models.connection import Connection, XeroTenant

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages multiple integrations (Xero, QuickBooks, etc.) using SQLAlchemy."""
    
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
    
    def __init__(self):
        """Initialize connection manager."""
        logger.info("ConnectionManager initialized with SQLAlchemy")
    
    def _get_db(self) -> Session:
        """Get database session."""
        return SessionLocal()
    
    def _connection_to_dict(self, conn: Connection) -> Dict[str, Any]:
        """Convert Connection model to dict format (for backward compatibility)."""
        tenants_list = []
        for tenant in conn.xero_tenants:
            tenants_list.append({
                "tenant_id": tenant.tenant_id,
                "tenant_name": tenant.tenant_name,
                "xero_connection_id": tenant.xero_connection_id
            })
        
        return {
            "id": conn.id,
            "category": conn.category,
            "software": conn.software,
            "name": conn.name,
            "access_token": conn.access_token,
            "refresh_token": conn.refresh_token,
            "expires_in": conn.expires_in,
            "token_created_at": conn.token_created_at,
            "created_at": conn.created_at,
            "updated_at": conn.updated_at,
            "metadata": conn.extra_metadata or {},  # Map extra_metadata back to metadata for compatibility
            "tenants": tenants_list
        }
    
    def get_all_connections(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all connections with xero_tenants loaded in one query (fixes N+1 problem).
        
        Args:
            tenant_id: Optional tenant ID to filter connections. If provided, only returns connections for this tenant.
        """
        db = self._get_db()
        try:
            # Eager load xero_tenants to avoid N+1 queries
            from sqlalchemy.orm import joinedload
            query = db.query(Connection).options(
                joinedload(Connection.xero_tenants)
            )
            
            # Filter by tenant_id if provided
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
        """Get a specific connection by ID with xero_tenants loaded (fixes N+1 problem) and in-memory caching.
        
        Args:
            connection_id: Connection ID to fetch
            tenant_id: Optional tenant ID to verify connection belongs to this tenant
        """
        from app.cache_manager import TwoTierCache
        
        def _fetch_from_db(conn_id: str):
            """Fetch connection from database."""
            db = self._get_db()
            try:
                # Eager load tenants to avoid N+1 queries
                from sqlalchemy.orm import joinedload
                query = db.query(Connection).options(
                    joinedload(Connection.xero_tenants)
                ).filter(Connection.id == conn_id)
                
                # Filter by tenant_id if provided
                if tenant_id:
                    query = query.filter(Connection.tenant_id == tenant_id)
                
                conn = query.first()
                if conn:
                    return self._connection_to_dict(conn)
                return None
            except SQLAlchemyError as e:
                logger.error(f"Error getting connection: {str(e)}")
                return None
            finally:
                db.close()
        
        # Use two-tier cache (in-memory + PostgreSQL)
        return TwoTierCache.get_connection(connection_id, _fetch_from_db)
    
    def add_connection(
        self,
        category: str,
        software: str,
        name: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        tenant_id: Optional[str] = None,
        tenant_name: Optional[str] = None,
        expires_in: int = 1800,
        metadata: Optional[Dict[str, Any]] = None,
        xero_connection_id: Optional[str] = None,
        tenants: Optional[List[Dict[str, Any]]] = None,
        tenant_id_param: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> str:
        """
        Add a new connection.
        
        Args:
            tenants: Optional list of tenant dicts with tenant_id, tenant_name, xero_connection_id.
                    If provided, this takes precedence over single tenant_id/tenant_name.
                    If not provided and tenant_id is set, creates tenants array with single tenant.
        """
        db = self._get_db()
        connection_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        try:
            # Create connection
            conn = Connection(
                id=connection_id,
                tenant_id=tenant_id_param,
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
            db.flush()  # Flush to get connection_id for foreign key
            
            # Build tenants list
            tenants_list = []
            if tenants:
                tenants_list = tenants
            elif tenant_id:
                tenants_list = [{
                    "tenant_id": tenant_id,
                    "tenant_name": tenant_name,
                    "xero_connection_id": xero_connection_id
                }]
            
            # Create tenant records
            for tenant_data in tenants_list:
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
            logger.info(f"Added connection: {name} ({software}) with {len(tenants_list)} tenant(s)")
            return connection_id
        except SQLAlchemyError as e:
            logger.error(f"Error adding connection: {str(e)}")
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
        tenant_id: Optional[str] = None,
        tenant_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        xero_connection_id: Optional[str] = None,
        tenants: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        Update an existing connection.
        
        Args:
            tenants: Optional list of tenant dicts to replace entire tenants array.
                    If provided, replaces all tenants. Otherwise, legacy single-tenant
                    fields (tenant_id, tenant_name, xero_connection_id) are ignored.
        """
        db = self._get_db()
        try:
            conn = db.query(Connection).filter(Connection.id == connection_id).first()
            if not conn:
                return False
            
            # Update connection fields
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
                # Merge with existing metadata
                existing_metadata = conn.extra_metadata or {}
                existing_metadata.update(metadata)
                conn.extra_metadata = existing_metadata
            
            # Handle tenants update
            if tenants is not None:
                # Replace all tenants
                # Delete existing tenants
                db.query(Tenant).filter(Tenant.connection_id == connection_id).delete()
                # Add new tenants
                now = datetime.now().isoformat()
                for tenant_data in tenants:
                    tenant = XeroTenant(
                        id=str(uuid.uuid4()),
                        connection_id=connection_id,
                        tenant_id=tenant_data.get("tenant_id"),
                        tenant_name=tenant_data.get("tenant_name", ""),
                        xero_connection_id=tenant_data.get("xero_connection_id"),
                        organization_id=organization_id,
                        created_at=now,
                        modified_at=now,
                        created_by=modified_by,  # Use modified_by for new tenants created during update
                        modified_by=modified_by
                    )
                    db.add(tenant)
            elif tenant_id is not None:
                # Legacy support: update single tenant (only if exactly one tenant exists)
                existing_tenants = db.query(Tenant).filter(Tenant.connection_id == connection_id).all()
                if len(existing_tenants) == 1:
                    existing_tenants[0].tenant_id = tenant_id
                    if tenant_name is not None:
                        existing_tenants[0].tenant_name = tenant_name
                    if xero_connection_id is not None:
                        existing_tenants[0].xero_connection_id = xero_connection_id
            
            conn.updated_at = datetime.now().isoformat()
            db.commit()
            logger.info(f"Updated connection: {connection_id}")
            
            # Invalidate in-memory cache after update
            from app.cache_manager import TwoTierCache
            TwoTierCache.invalidate_connection(connection_id)
            logger.debug(f"Invalidated connection cache for: {connection_id}")
            
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
            
            db.delete(conn)  # Cascade will delete tenants
            db.commit()
            logger.info(f"Deleted connection: {connection_id}")
            
            # Invalidate in-memory cache after deletion
            from app.cache_manager import TwoTierCache
            TwoTierCache.invalidate_connection(connection_id)
            logger.debug(f"Invalidated connection cache for deleted connection: {connection_id}")
            
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
    
    def get_connections_by_category(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get connections grouped by category."""
        connections = self.get_all_connections()
        grouped = {}
        
        for conn in connections:
            category = conn.get("category", "finance")
            if category not in grouped:
                grouped[category] = []
            grouped[category].append(conn)
        
        return grouped
    
    def get_active_connections(self, software: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all active connections (with valid access tokens).
        
        Args:
            software: Optional filter by software type (e.g., "xero", "quickbooks")
            
        Returns:
            List of active connections
        """
        connections = self.get_all_connections()
        active = []
        
        for conn in connections:
            # Check if connection has access token
            if conn.get("access_token"):
                # Check if token is expired
                if not self.is_token_expired(conn["id"]):
                    # Filter by software if specified
                    if software is None or conn.get("software") == software:
                        active.append(conn)
        
        return active
    
    def get_active_connection(self, software: str, connection_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get a single active connection for a software type.
        
        Args:
            software: Software type (e.g., "xero", "quickbooks")
            connection_id: Optional specific connection ID to retrieve
            
        Returns:
            Active connection dict or None if not found
        """
        if connection_id:
            conn = self.get_connection(connection_id)
            if conn and conn.get("access_token") and not self.is_token_expired(connection_id):
                if conn.get("software") == software:
                    return conn
            return None
        
        # Get first active connection for this software
        active = self.get_active_connections(software=software)
        return active[0] if active else None
    
    def get_connections_by_refresh_token(self, refresh_token: str, software: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Find all connections sharing the same refresh_token.
        Useful for token synchronization across multiple tenants from the same OAuth authorization.
        
        Args:
            refresh_token: The refresh token to search for
            software: Optional filter by software type (e.g., "xero")
            
        Returns:
            List of connections sharing the refresh_token
        """
        if not refresh_token:
            return []
        
        db = self._get_db()
        try:
            from sqlalchemy.orm import joinedload
            query = db.query(Connection).options(
                joinedload(Connection.xero_tenants)
            ).filter(Connection.refresh_token == refresh_token)
            if software:
                query = query.filter(Connection.software == software)
            
            connections = query.all()
            return [self._connection_to_dict(conn) for conn in connections]
        except SQLAlchemyError as e:
            logger.error(f"Error getting connections by refresh_token: {str(e)}")
            return []
        finally:
            db.close()
    
    def sync_tokens_for_refresh_token(
        self,
        refresh_token: str,
        new_access_token: str,
        new_refresh_token: str,
        expires_in: int,
        software: Optional[str] = None
    ) -> int:
        """
        Update all connections sharing the same refresh_token with new tokens.
        This ensures token synchronization across multiple tenants from the same OAuth authorization.
        
        Args:
            refresh_token: The old refresh token to find connections
            new_access_token: New access token to set
            new_refresh_token: New refresh token to set (may be same as old or different)
            expires_in: Token expiration time in seconds
            software: Optional filter by software type (e.g., "xero")
            
        Returns:
            Number of connections updated
        """
        connections_to_update = self.get_connections_by_refresh_token(refresh_token, software=software)
        
        if not connections_to_update:
            logger.info(f"No connections found with refresh_token to sync")
            return 0
        
        updated_count = 0
        for conn in connections_to_update:
            connection_id = conn.get("id")
            try:
                success = self.update_connection(
                    connection_id,
                    access_token=new_access_token,
                    refresh_token=new_refresh_token,
                    expires_in=expires_in
                )
                if success:
                    updated_count += 1
                    logger.info(f"Synced tokens for connection {connection_id} ({conn.get('name', 'Unknown')})")
                else:
                    logger.warning(f"Failed to sync tokens for connection {connection_id}")
            except Exception as e:
                logger.error(f"Error syncing tokens for connection {connection_id}: {str(e)}")
        
        logger.info(f"Token synchronization complete: {updated_count}/{len(connections_to_update)} connections updated")
        return updated_count
    
    def get_all_xero_connections(self) -> List[Dict[str, Any]]:
        """
        Get all Xero connections (active and expired).
        Useful for aggregated views across multiple tenants.
        
        Returns:
            List of all Xero connections
        """
        db = self._get_db()
        try:
            from sqlalchemy.orm import joinedload
            connections = db.query(Connection).options(
                joinedload(Connection.xero_tenants)
            ).filter(Connection.software == "xero").all()
            return [self._connection_to_dict(conn) for conn in connections]
        except SQLAlchemyError as e:
            logger.error(f"Error getting Xero connections: {str(e)}")
            return []
        finally:
            db.close()
    
    def get_connections_by_tenant_ids(self, tenant_ids: List[str], software: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get connections for specific tenant IDs.
        Useful for fetching data from specific tenants.
        
        Args:
            tenant_ids: List of tenant IDs to find
            software: Optional filter by software type (e.g., "xero")
            
        Returns:
            List of connections matching the tenant IDs
        """
        db = self._get_db()
        try:
            from sqlalchemy.orm import joinedload
            query = db.query(Connection).options(
                joinedload(Connection.xero_tenants)
            ).join(XeroTenant).filter(XeroTenant.tenant_id.in_(tenant_ids))
            if software:
                query = query.filter(Connection.software == software)
            
            connections = query.distinct().all()
            return [self._connection_to_dict(conn) for conn in connections]
        except SQLAlchemyError as e:
            logger.error(f"Error getting connections by tenant_ids: {str(e)}")
            return []
        finally:
            db.close()
    
    def get_connection_by_refresh_token(self, refresh_token: str, software: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Find a connection with matching refresh_token.
        Useful for grouping tenants from the same OAuth authorization.
        
        Args:
            refresh_token: The refresh token to search for
            software: Optional filter by software type (e.g., "xero")
            
        Returns:
            Connection dict or None if not found
        """
        connections = self.get_connections_by_refresh_token(refresh_token, software=software)
        return connections[0] if connections else None
    
    def add_tenant(self, connection_id: str, tenant_id: str, tenant_name: str, xero_connection_id: str) -> bool:
        """
        Add a tenant to an existing connection.
        
        Args:
            connection_id: Connection to add tenant to
            tenant_id: Tenant ID
            tenant_name: Tenant name
            xero_connection_id: Xero connection ID for disconnecting
            
        Returns:
            True if added, False if tenant already exists or connection not found
        """
        db = self._get_db()
        try:
            # Check if connection exists
            conn = db.query(Connection).filter(Connection.id == connection_id).first()
            if not conn:
                return False
            
            # Check if tenant already exists
            existing = db.query(Tenant).filter(
                Tenant.connection_id == connection_id,
                Tenant.tenant_id == tenant_id
            ).first()
            
            if existing:
                logger.info(f"Tenant {tenant_id} already exists in connection {connection_id}")
                return False
            
            # Add tenant
            tenant = Tenant(
                id=str(uuid.uuid4()),
                connection_id=connection_id,
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                xero_connection_id=xero_connection_id,
                created_at=datetime.now().isoformat()
            )
            db.add(tenant)
            
            # Update connection updated_at
            conn.updated_at = datetime.now().isoformat()
            
            db.commit()
            logger.info(f"Added tenant {tenant_name} ({tenant_id}) to connection {connection_id}")
            
            # Invalidate in-memory cache after adding tenant
            from app.cache_manager import TwoTierCache
            TwoTierCache.invalidate_connection(connection_id)
            logger.debug(f"Invalidated connection cache after adding tenant: {connection_id}")
            
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error adding tenant: {str(e)}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def remove_tenant(self, connection_id: str, tenant_id: str) -> bool:
        """
        Remove a tenant from a connection.
        
        Args:
            connection_id: Connection to remove tenant from
            tenant_id: Tenant ID to remove
            
        Returns:
            True if removed, False if tenant not found or connection not found
        """
        db = self._get_db()
        try:
            tenant = db.query(Tenant).filter(
                Tenant.connection_id == connection_id,
                Tenant.tenant_id == tenant_id
            ).first()
            
            if not tenant:
                return False
            
            # Update connection updated_at
            conn = db.query(Connection).filter(Connection.id == connection_id).first()
            if conn:
                conn.updated_at = datetime.now().isoformat()
            
            db.delete(tenant)
            db.commit()
            logger.info(f"Removed tenant {tenant_id} from connection {connection_id}")
            
            # Invalidate in-memory cache after removing tenant
            from app.cache_manager import TwoTierCache
            TwoTierCache.invalidate_connection(connection_id)
            logger.debug(f"Invalidated connection cache after removing tenant: {connection_id}")
            
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error removing tenant: {str(e)}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def cleanup_duplicate_connections(self) -> int:
        """
        Clean up duplicate connections that share the same refresh_token.
        For each refresh_token group, keeps the oldest connection and merges tenants from others.
        Then deletes the duplicate connections.
        
        Returns:
            Number of duplicate connections removed
        """
        from collections import defaultdict
        
        db = self._get_db()
        try:
            from sqlalchemy.orm import joinedload
            # Get all Xero connections with tenants loaded
            xero_connections = db.query(Connection).options(
                joinedload(Connection.xero_tenants)
            ).filter(Connection.software == "xero").all()
            
            # Group by refresh_token
            refresh_token_groups = defaultdict(list)
            for conn in xero_connections:
                if conn.refresh_token:
                    refresh_token_groups[conn.refresh_token].append(conn)
            
            deleted_count = 0
            
            # Process each group
            for refresh_token, connections_list in refresh_token_groups.items():
                if len(connections_list) <= 1:
                    continue  # No duplicates
                
                # Sort by created_at (oldest first)
                connections_list.sort(key=lambda x: x.created_at or "")
                
                # Keep the oldest connection
                keep_conn = connections_list[0]
                
                # Collect all unique tenants from all connections in this group
                all_tenants = {}
                for conn in connections_list:
                    for tenant in conn.xero_tenants:
                        tenant_id = tenant.tenant_id
                        if tenant_id:
                            # Use the most recent tenant info
                            if tenant_id not in all_tenants:
                                all_tenants[tenant_id] = tenant
                            elif tenant.xero_connection_id and not all_tenants[tenant_id].xero_connection_id:
                                all_tenants[tenant_id] = tenant
                
                # Delete old tenants from kept connection and add merged ones
                db.query(Tenant).filter(Tenant.connection_id == keep_conn.id).delete()
                
                # Add merged tenants
                now = datetime.now().isoformat()
                for tenant in all_tenants.values():
                    new_tenant = XeroTenant(
                        id=str(uuid.uuid4()),
                        connection_id=keep_conn.id,
                        tenant_id=tenant.tenant_id,
                        tenant_name=tenant.tenant_name,
                        xero_connection_id=tenant.xero_connection_id,
                        created_at=now
                    )
                    db.add(new_tenant)
                
                # Use the most recent token info
                most_recent_conn = max(connections_list, key=lambda x: x.updated_at or "")
                keep_conn.access_token = most_recent_conn.access_token
                keep_conn.refresh_token = most_recent_conn.refresh_token
                keep_conn.expires_in = most_recent_conn.expires_in
                if most_recent_conn.token_created_at:
                    keep_conn.token_created_at = most_recent_conn.token_created_at
                keep_conn.updated_at = datetime.now().isoformat()
                
                logger.info(f"Merged {len(connections_list)} connections with refresh_token {refresh_token[:20]}... into {keep_conn.id}")
                logger.info(f"  Kept connection: {keep_conn.id} (created: {keep_conn.created_at or 'N/A'})")
                logger.info(f"  Merged {len(all_tenants)} unique tenant(s)")
                
                # Delete all other connections in this group
                for conn in connections_list[1:]:
                    db.delete(conn)
                    deleted_count += 1
                    logger.info(f"  Deleted duplicate: {conn.id}")
            
            if deleted_count > 0:
                db.commit()
                logger.info(f"Cleanup complete: Removed {deleted_count} duplicate connection(s)")
                
                # Invalidate cache for all affected connections
                from app.cache_manager import TwoTierCache
                for refresh_token, connections_list in refresh_token_groups.items():
                    if len(connections_list) > 1:
                        # Invalidate cache for kept connection
                        keep_conn = connections_list[0]
                        TwoTierCache.invalidate_connection(keep_conn.id)
                        # Invalidate cache for deleted connections
                        for conn in connections_list[1:]:
                            TwoTierCache.invalidate_connection(conn.id)
                logger.debug(f"Invalidated cache for all connections affected by cleanup")
            
            return deleted_count
        except SQLAlchemyError as e:
            logger.error(f"Error cleaning up duplicate connections: {str(e)}")
            db.rollback()
            return 0
        finally:
            db.close()
    
    def get_all_tenants_for_connection(self, connection_id: str) -> List[Dict[str, Any]]:
        """
        Get all tenants for a connection.
        
        Args:
            connection_id: Connection ID
            
        Returns:
            List of tenant dicts
        """
        db = self._get_db()
        try:
            from sqlalchemy.orm import joinedload
            conn = db.query(Connection).options(
                joinedload(Connection.xero_tenants)
            ).filter(Connection.id == connection_id).first()
            if not conn:
                return []
            
            tenants = []
            for tenant in conn.xero_tenants:
                tenants.append({
                    "tenant_id": tenant.tenant_id,
                    "tenant_name": tenant.tenant_name,
                    "xero_connection_id": tenant.xero_connection_id
                })
            
            return tenants
        except SQLAlchemyError as e:
            logger.error(f"Error getting tenants for connection: {str(e)}")
            return []
        finally:
            db.close()


# Global connection manager instance
connection_manager = ConnectionManager()

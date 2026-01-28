"""Connection management for multiple integrations."""
import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Connection storage file
CONNECTIONS_FILE = Path("connections.json")


class ConnectionManager:
    """Manages multiple integrations (Xero, QuickBooks, etc.)."""
    
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
        self.connections_file = CONNECTIONS_FILE
        self._ensure_connections_file()
    
    def _ensure_connections_file(self):
        """Ensure connections file exists."""
        if not self.connections_file.exists():
            self._save_connections({})
    
    def _load_connections(self) -> Dict[str, Any]:
        """Load connections from file."""
        try:
            if self.connections_file.exists():
                with open(self.connections_file, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Error loading connections: {str(e)}")
            return {}
    
    def _save_connections(self, connections: Dict[str, Any]):
        """Save connections to file."""
        try:
            with open(self.connections_file, 'w') as f:
                json.dump(connections, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving connections: {str(e)}")
            raise
    
    def get_all_connections(self) -> List[Dict[str, Any]]:
        """Get all connections."""
        data = self._load_connections()
        connections = []
        for conn_id, conn_data in data.items():
            conn_data['id'] = conn_id
            connections.append(conn_data)
        return connections
    
    def get_connection(self, connection_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific connection by ID."""
        data = self._load_connections()
        if connection_id in data:
            conn = data[connection_id].copy()
            conn['id'] = connection_id
            return conn
        return None
    
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
        tenants: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Add a new connection.
        
        Args:
            tenants: Optional list of tenant dicts with tenant_id, tenant_name, xero_connection_id.
                    If provided, this takes precedence over single tenant_id/tenant_name.
                    If not provided and tenant_id is set, creates tenants array with single tenant.
        """
        import uuid
        connection_id = str(uuid.uuid4())
        
        # Build tenants array
        tenants_list = []
        if tenants:
            tenants_list = tenants
        elif tenant_id:
            # Legacy support: convert single tenant to tenants array
            tenants_list = [{
                "tenant_id": tenant_id,
                "tenant_name": tenant_name,
                "xero_connection_id": xero_connection_id
            }]
        
        data = self._load_connections()
        data[connection_id] = {
            "category": category,
            "software": software,
            "name": name,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
            "token_created_at": datetime.now().isoformat(),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "metadata": metadata or {},
            "tenants": tenants_list  # Array of tenants
        }
        
        self._save_connections(data)
        logger.info(f"Added connection: {name} ({software}) with {len(tenants_list)} tenant(s)")
        return connection_id
    
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
        data = self._load_connections()
        if connection_id not in data:
            return False
        
        # Ensure tenants array exists (for backward compatibility)
        if "tenants" not in data[connection_id]:
            # Migrate old format to new format
            old_tenant_id = data[connection_id].get("tenant_id")
            old_tenant_name = data[connection_id].get("tenant_name")
            old_xero_connection_id = data[connection_id].get("xero_connection_id")
            if old_tenant_id:
                data[connection_id]["tenants"] = [{
                    "tenant_id": old_tenant_id,
                    "tenant_name": old_tenant_name,
                    "xero_connection_id": old_xero_connection_id
                }]
            else:
                data[connection_id]["tenants"] = []
        
        if name is not None:
            data[connection_id]["name"] = name
        if access_token is not None:
            data[connection_id]["access_token"] = access_token
        if refresh_token is not None:
            data[connection_id]["refresh_token"] = refresh_token
        if expires_in is not None:
            data[connection_id]["expires_in"] = expires_in
            data[connection_id]["token_created_at"] = datetime.now().isoformat()
        if tenants is not None:
            data[connection_id]["tenants"] = tenants
        elif tenant_id is not None:
            # Legacy support: update single tenant (only if tenants array has one tenant)
            if len(data[connection_id]["tenants"]) == 1:
                data[connection_id]["tenants"][0]["tenant_id"] = tenant_id
                if tenant_name is not None:
                    data[connection_id]["tenants"][0]["tenant_name"] = tenant_name
                if xero_connection_id is not None:
                    data[connection_id]["tenants"][0]["xero_connection_id"] = xero_connection_id
        if metadata is not None:
            data[connection_id]["metadata"].update(metadata)
        
        data[connection_id]["updated_at"] = datetime.now().isoformat()
        self._save_connections(data)
        logger.info(f"Updated connection: {connection_id}")
        return True
    
    def delete_connection(self, connection_id: str) -> bool:
        """Delete a connection."""
        data = self._load_connections()
        if connection_id in data:
            del data[connection_id]
            self._save_connections(data)
            logger.info(f"Deleted connection: {connection_id}")
            return True
        return False
    
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
        
        connections = self.get_all_connections()
        matching = []
        
        for conn in connections:
            conn_refresh_token = conn.get("refresh_token")
            if conn_refresh_token == refresh_token:
                # Apply software filter if specified
                if software is None or conn.get("software") == software:
                    matching.append(conn)
        
        return matching
    
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
        connections = self.get_all_connections()
        return [conn for conn in connections if conn.get("software") == "xero"]
    
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
        connections = self.get_all_connections()
        matching = []
        
        tenant_ids_set = set(tenant_ids)
        for conn in connections:
            # Check tenants array
            tenants = conn.get("tenants", [])
            for tenant in tenants:
                if tenant.get("tenant_id") in tenant_ids_set:
                    if software is None or conn.get("software") == software:
                        matching.append(conn)
                        break  # Found tenant in this connection, move to next connection
        
        return matching
    
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
        if not refresh_token:
            return None
        
        connections = self.get_all_connections()
        for conn in connections:
            conn_refresh_token = conn.get("refresh_token")
            if conn_refresh_token == refresh_token:
                if software is None or conn.get("software") == software:
                    return conn
        
        return None
    
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
        data = self._load_connections()
        if connection_id not in data:
            return False
        
        # Ensure tenants array exists
        if "tenants" not in data[connection_id]:
            data[connection_id]["tenants"] = []
        
        # Check if tenant already exists
        tenants = data[connection_id]["tenants"]
        for tenant in tenants:
            if tenant.get("tenant_id") == tenant_id:
                logger.info(f"Tenant {tenant_id} already exists in connection {connection_id}")
                return False
        
        # Add tenant
        tenants.append({
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "xero_connection_id": xero_connection_id
        })
        
        data[connection_id]["updated_at"] = datetime.now().isoformat()
        self._save_connections(data)
        logger.info(f"Added tenant {tenant_name} ({tenant_id}) to connection {connection_id}")
        return True
    
    def remove_tenant(self, connection_id: str, tenant_id: str) -> bool:
        """
        Remove a tenant from a connection.
        
        Args:
            connection_id: Connection to remove tenant from
            tenant_id: Tenant ID to remove
            
        Returns:
            True if removed, False if tenant not found or connection not found
        """
        data = self._load_connections()
        if connection_id not in data:
            return False
        
        # Ensure tenants array exists
        if "tenants" not in data[connection_id]:
            data[connection_id]["tenants"] = []
        
        tenants = data[connection_id]["tenants"]
        original_count = len(tenants)
        
        # Remove tenant
        data[connection_id]["tenants"] = [
            t for t in tenants if t.get("tenant_id") != tenant_id
        ]
        
        if len(data[connection_id]["tenants"]) < original_count:
            data[connection_id]["updated_at"] = datetime.now().isoformat()
            self._save_connections(data)
            logger.info(f"Removed tenant {tenant_id} from connection {connection_id}")
            return True
        
        return False
    
    def get_all_tenants_for_connection(self, connection_id: str) -> List[Dict[str, Any]]:
        """
        Get all tenants for a connection.
        
        Args:
            connection_id: Connection ID
            
        Returns:
            List of tenant dicts
        """
        conn = self.get_connection(connection_id)
        if not conn:
            return []
        
        # Ensure tenants array exists (migrate if needed)
        if "tenants" not in conn:
            old_tenant_id = conn.get("tenant_id")
            if old_tenant_id:
                return [{
                    "tenant_id": old_tenant_id,
                    "tenant_name": conn.get("tenant_name"),
                    "xero_connection_id": conn.get("xero_connection_id")
                }]
            return []
        
        return conn.get("tenants", [])


# Global connection manager instance
connection_manager = ConnectionManager()

"""PostgreSQL-based cache for MCP data with connection and tenant tracking."""
import json
import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models.mcp_cache import MCPDataCache

logger = logging.getLogger(__name__)


class DataCache:
    """PostgreSQL-based cache for MCP data, scoped by connection and Xero tenant."""
    
    def __init__(self, connection_id: Optional[str] = None, xero_tenant_id: Optional[str] = None, tenant_id: Optional[str] = None):
        """
        Initialize cache with connection and Xero tenant context.
        
        Args:
            connection_id: Connection ID (required for set operations)
            xero_tenant_id: Xero/QuickBooks tenant ID (required for set operations)
            tenant_id: B2B SaaS tenant ID (optional, for data segregation)
        """
        self.connection_id = connection_id
        self.xero_tenant_id = xero_tenant_id  # Xero tenant ID
        self.tenant_id = tenant_id  # B2B SaaS tenant ID (for data segregation)
        logger.info(f"DataCache initialized for connection_id={connection_id}, xero_tenant_id={xero_tenant_id}, tenant_id={tenant_id}")
    
    def _get_db(self) -> Session:
        """Get database session."""
        return SessionLocal()
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get cached data by key for the current connection and tenant.
        Uses two-tier caching: in-memory LRU + PostgreSQL.
        
        Args:
            key: Cache key (e.g., "organisation", "accounts")
            
        Returns:
            Dict with "data" and "cached_at" keys, or None if not found
        """
        if not self.connection_id or not self.xero_tenant_id:
            logger.warning(f"Cannot get cache for key {key}: connection_id or xero_tenant_id not set")
            return None
        
        from app.cache_manager import TwoTierCache
        
        def _fetch_from_db(connection_id: str, xero_tenant_id: str, cache_key: str):
            """Fetch from PostgreSQL database."""
            db = self._get_db()
            try:
                # Optimize: Only fetch data and cached_at columns (not full row)
                query = db.query(
                    MCPDataCache.data,
                    MCPDataCache.cached_at
                ).filter(
                    MCPDataCache.connection_id == connection_id,
                    MCPDataCache.xero_tenant_id == xero_tenant_id,
                    MCPDataCache.cache_key == cache_key
                )
                
                # Filter by tenant_id (B2B SaaS) if available
                if self.tenant_id:
                    query = query.filter(MCPDataCache.tenant_id == self.tenant_id)
                
                cache_entry = query.first()
                
                if cache_entry:
                    logger.debug(f"Cache hit in PostgreSQL for key: {key}")
                    # Parse JSON data
                    try:
                        data = json.loads(cache_entry.data)
                        return {
                            "data": data,
                            "cached_at": cache_entry.cached_at
                        }
                    except json.JSONDecodeError as e:
                        logger.error(f"Error parsing cached data for key {key}: {e}")
                        return None
                
                logger.debug(f"Cache miss in PostgreSQL for key: {key}")
                return None
            except SQLAlchemyError as e:
                logger.error(f"Error getting cache for key {key}: {str(e)}")
                return None
            finally:
                db.close()
        
        # Use two-tier cache (in-memory + PostgreSQL)
        return TwoTierCache.get_mcp_data(
            self.connection_id,
            self.xero_tenant_id,
            key,
            _fetch_from_db
        )
    
    def set(self, key: str, value: Any):
        """
        Set cached data for key, scoped to connection and tenant.
        
        Args:
            key: Cache key (e.g., "organisation", "accounts")
            value: Data to cache (will be JSON serialized)
        """
        if not self.connection_id or not self.xero_tenant_id:
            logger.warning(f"Cannot set cache for key {key}: connection_id={self.connection_id}, xero_tenant_id={self.xero_tenant_id} not set")
            return
        
        logger.info(f"Attempting to cache key={key} for connection_id={self.connection_id}, xero_tenant_id={self.xero_tenant_id}")
        
        db = self._get_db()
        try:
            # Serialize value to JSON
            try:
                data_json = json.dumps(value, default=str, ensure_ascii=False)
                logger.debug(f"Serialized data for key {key}: {len(data_json)} bytes")
            except (TypeError, ValueError) as e:
                logger.error(f"Error serializing cache data for key {key}: {str(e)}", exc_info=True)
                return
            
            cached_at = datetime.utcnow().isoformat()
            
            # Check if entry exists
            query = db.query(MCPDataCache).filter(
                MCPDataCache.connection_id == self.connection_id,
                MCPDataCache.xero_tenant_id == self.xero_tenant_id,
                MCPDataCache.cache_key == key
            )
            if self.tenant_id:
                query = query.filter(MCPDataCache.tenant_id == self.tenant_id)
            existing = query.first()
            
            if existing:
                # Update existing entry
                existing.data = data_json
                existing.cached_at = cached_at
                logger.info(f"Updated cache for key: {key} (connection_id={self.connection_id}, xero_tenant_id={self.xero_tenant_id})")
            else:
                # Create new entry
                cache_entry = MCPDataCache(
                    id=str(uuid.uuid4()),
                    tenant_id=self.tenant_id,  # B2B SaaS tenant ID
                    connection_id=self.connection_id,
                    xero_tenant_id=self.xero_tenant_id,  # Xero tenant ID
                    cache_key=key,
                    data=data_json,
                    cached_at=cached_at
                )
                db.add(cache_entry)
                logger.info(f"Cached data for key: {key} (connection_id={self.connection_id}, xero_tenant_id={self.xero_tenant_id}, data_size={len(data_json)} bytes)")
            
            db.commit()
            logger.info(f"✅ Successfully committed cache entry for key: {key} to PostgreSQL")
            
            # Also update in-memory cache
            try:
                from app.cache_manager import TwoTierCache
                cache_value = {
                    "data": value,
                    "cached_at": cached_at
                }
                # Store in in-memory cache (already stored in DB above)
                mcp_cache_key = TwoTierCache.get_mcp_cache_key(self.connection_id, self.xero_tenant_id, key)
                from app.cache_manager import _mcp_cache
                _mcp_cache.set(mcp_cache_key, cache_value)
                logger.debug(f"✅ Also cached in memory: {key}")
            except Exception as e:
                logger.warning(f"Failed to cache in memory for key {key}: {str(e)}")
                # Don't fail the whole operation if in-memory cache fails
        except SQLAlchemyError as e:
            logger.error(f"❌ Database error setting cache for key {key}: {str(e)}", exc_info=True)
            db.rollback()
        except Exception as e:
            logger.error(f"❌ Unexpected error setting cache for key {key}: {str(e)}", exc_info=True)
            db.rollback()
        finally:
            db.close()
    
    def has(self, key: str) -> bool:
        """
        Check if key exists in cache for the current connection and tenant.
        
        Args:
            key: Cache key
            
        Returns:
            True if cached data exists, False otherwise
        """
        if not self.connection_id or not self.xero_tenant_id:
            return False
        
        db = self._get_db()
        try:
            query = db.query(MCPDataCache).filter(
                MCPDataCache.connection_id == self.connection_id,
                MCPDataCache.xero_tenant_id == self.xero_tenant_id,
                MCPDataCache.cache_key == key
            )
            if self.tenant_id:
                query = query.filter(MCPDataCache.tenant_id == self.tenant_id)
            exists = query.first() is not None
            return exists
        except SQLAlchemyError as e:
            logger.error(f"Error checking cache for key {key}: {str(e)}")
            return False
        finally:
            db.close()
    
    def clear(self, connection_id: Optional[str] = None, tenant_id: Optional[str] = None):
        """
        Clear cached data.
        
        Args:
            connection_id: If provided, clear only for this connection
            tenant_id: If provided, clear only for this tenant
                          (requires connection_id to be provided)
        """
        db = self._get_db()
        try:
            query = db.query(MCPDataCache)
            
            if connection_id:
                query = query.filter(MCPDataCache.connection_id == connection_id)
                if tenant_id:
                    query = query.filter(MCPDataCache.tenant_id == tenant_id)
            else:
                # Clear all if no filters
                query = query.filter(False)  # This will delete nothing, but we'll use delete() directly
            
            if connection_id:
                deleted_count = query.delete()
                db.commit()
                logger.info(f"Cleared {deleted_count} cache entries (connection_id={connection_id}, tenant_id={tenant_id})")
            else:
                # Clear all cache entries
                deleted_count = db.query(MCPDataCache).delete()
                db.commit()
                logger.info(f"Cleared all {deleted_count} cache entries")
        except SQLAlchemyError as e:
            logger.error(f"Error clearing cache: {str(e)}")
            db.rollback()
        finally:
            db.close()
    
    def get_all_keys(self, connection_id: Optional[str] = None, tenant_id: Optional[str] = None) -> list:
        """
        Get all cache keys.
        
        Args:
            connection_id: If provided, get keys only for this connection
            tenant_id: If provided, get keys only for this tenant
                          (requires connection_id to be provided)
        
        Returns:
            List of cache keys
        """
        db = self._get_db()
        try:
            query = db.query(MCPDataCache.cache_key)
            
            if connection_id:
                query = query.filter(MCPDataCache.connection_id == connection_id)
                if tenant_id:
                    query = query.filter(MCPDataCache.xero_tenant_id == tenant_id)
            
            keys = [row[0] for row in query.distinct().all()]
            return keys
        except SQLAlchemyError as e:
            logger.error(f"Error getting cache keys: {str(e)}")
            return []
        finally:
            db.close()
    
    def invalidate(self, key: str):
        """
        Remove a specific key from cache for the current connection and tenant.
        
        Args:
            key: Cache key to invalidate
        """
        if not self.connection_id or not self.xero_tenant_id:
            logger.warning(f"Cannot invalidate cache for key {key}: connection_id or xero_tenant_id not set")
            return
        
        db = self._get_db()
        try:
            query = db.query(MCPDataCache).filter(
                MCPDataCache.connection_id == self.connection_id,
                MCPDataCache.xero_tenant_id == self.xero_tenant_id,
                MCPDataCache.cache_key == key
            )
            if self.tenant_id:
                query = query.filter(MCPDataCache.tenant_id == self.tenant_id)
            deleted_count = query.delete()
            
            if deleted_count > 0:
                db.commit()
                logger.info(f"Invalidated cache for key: {key}")
            else:
                logger.debug(f"No cache entry found for key: {key}")
        except SQLAlchemyError as e:
            logger.error(f"Error invalidating cache for key {key}: {str(e)}")
            db.rollback()
        finally:
            db.close()
    
    def get_for_connection_tenant(self, connection_id: str, tenant_id: str, key: str) -> Optional[Any]:
        """
        Get cached data for a specific connection and tenant (static method style).
        
        Args:
            connection_id: Connection ID
            tenant_id: Tenant ID
            key: Cache key
            
        Returns:
            Dict with "data" and "cached_at" keys, or None if not found
        """
        db = self._get_db()
        try:
            cache_entry = db.query(MCPDataCache).filter(
                MCPDataCache.connection_id == connection_id,
                MCPDataCache.xero_tenant_id == tenant_id,
                MCPDataCache.cache_key == key
            ).first()
            
            if cache_entry:
                try:
                    data = json.loads(cache_entry.data)
                    return {
                        "data": data,
                        "cached_at": cache_entry.cached_at
                    }
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing cached data: {e}")
                    return None
            
            return None
        except SQLAlchemyError as e:
            logger.error(f"Error getting cache: {str(e)}")
            return None
        finally:
            db.close()
    
    def exists_for_connection_tenant(self, connection_id: str, tenant_id: str, key: str) -> bool:
        """
        Check if cached data exists for a specific connection and tenant.
        
        Args:
            connection_id: Connection ID
            tenant_id: Tenant ID
            key: Cache key
            
        Returns:
            True if cached data exists, False otherwise
        """
        db = self._get_db()
        try:
            exists = db.query(MCPDataCache).filter(
                MCPDataCache.connection_id == connection_id,
                MCPDataCache.tenant_id == tenant_id,
                MCPDataCache.cache_key == key
            ).first() is not None
            return exists
        except SQLAlchemyError as e:
            logger.error(f"Error checking cache existence: {str(e)}")
            return False
        finally:
            db.close()

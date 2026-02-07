"""Two-tier cache: In-memory LRU cache + PostgreSQL for persistence."""
import json
import logging
import threading
from functools import lru_cache
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import OrderedDict

logger = logging.getLogger(__name__)


class LRUCache:
    """Thread-safe LRU cache with TTL support."""
    
    def __init__(self, maxsize: int = 128, ttl_seconds: int = 300):
        """
        Initialize LRU cache.
        
        Args:
            maxsize: Maximum number of items to cache
            ttl_seconds: Time to live in seconds (default 5 minutes)
        """
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: Dict[str, datetime] = {}
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get item from cache if not expired."""
        with self._lock:
            if key not in self._cache:
                return None
            
            # Check if expired
            if key in self._timestamps:
                age = (datetime.now() - self._timestamps[key]).total_seconds()
                if age > self.ttl_seconds:
                    # Expired, remove it
                    del self._cache[key]
                    del self._timestamps[key]
                    return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return self._cache[key]
    
    def set(self, key: str, value: Any):
        """Set item in cache."""
        with self._lock:
            if key in self._cache:
                # Update existing
                self._cache.move_to_end(key)
            elif len(self._cache) >= self.maxsize:
                # Remove oldest (first item)
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                if oldest_key in self._timestamps:
                    del self._timestamps[oldest_key]
            
            self._cache[key] = value
            self._timestamps[key] = datetime.now()
    
    def delete(self, key: str):
        """Delete item from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
            if key in self._timestamps:
                del self._timestamps[key]
    
    def clear(self):
        """Clear all items from cache."""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()
    
    def size(self) -> int:
        """Get current cache size."""
        with self._lock:
            return len(self._cache)


# Global in-memory caches
_connection_cache = LRUCache(maxsize=64, ttl_seconds=300)  # 5 minutes TTL
_mcp_cache = LRUCache(maxsize=256, ttl_seconds=600)  # 10 minutes TTL for MCP data


class TwoTierCache:
    """Two-tier cache: Fast in-memory LRU + Persistent PostgreSQL."""
    
    @staticmethod
    def get_connection_cache_key(connection_id: str) -> str:
        """Generate cache key for connection."""
        return f"conn:{connection_id}"
    
    @staticmethod
    def get_mcp_cache_key(connection_id: str, tenant_id: str, cache_key: str) -> str:
        """Generate cache key for MCP data."""
        return f"mcp:{connection_id}:{tenant_id}:{cache_key}"
    
    @staticmethod
    def get_connection(connection_id: str, db_fetch_func) -> Optional[Dict[str, Any]]:
        """
        Get connection with two-tier caching.
        
        Args:
            connection_id: Connection ID
            db_fetch_func: Function to fetch from database if cache miss
            
        Returns:
            Connection dict or None
        """
        cache_key = TwoTierCache.get_connection_cache_key(connection_id)
        
        # Try in-memory cache first
        cached = _connection_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Connection cache HIT (in-memory): {connection_id}")
            return cached
        
        # Cache miss - fetch from database
        logger.debug(f"Connection cache MISS (in-memory): {connection_id}, fetching from DB")
        result = db_fetch_func(connection_id)
        
        # Store in cache if found
        if result:
            _connection_cache.set(cache_key, result)
            logger.debug(f"Cached connection in memory: {connection_id}")
        
        return result
    
    @staticmethod
    def get_mcp_data(connection_id: str, tenant_id: str, cache_key: str, db_fetch_func) -> Optional[Any]:
        """
        Get MCP data with two-tier caching.
        
        Args:
            connection_id: Connection ID
            tenant_id: Tenant ID
            cache_key: Cache key (e.g., "organisation", "accounts")
            db_fetch_func: Function to fetch from database if cache miss
            
        Returns:
            Cached data or None
        """
        mcp_cache_key = TwoTierCache.get_mcp_cache_key(connection_id, tenant_id, cache_key)
        
        # Try in-memory cache first
        cached = _mcp_cache.get(mcp_cache_key)
        if cached is not None:
            logger.debug(f"MCP cache HIT (in-memory): {cache_key} for {connection_id}:{tenant_id}")
            return cached
        
        # Cache miss - fetch from database
        logger.debug(f"MCP cache MISS (in-memory): {cache_key} for {connection_id}:{tenant_id}, fetching from DB")
        result = db_fetch_func(connection_id, tenant_id, cache_key)
        
        # Store in cache if found
        if result:
            _mcp_cache.set(mcp_cache_key, result)
            logger.debug(f"Cached MCP data in memory: {cache_key} for {connection_id}:{tenant_id}")
        
        return result
    
    @staticmethod
    def set_mcp_data(connection_id: str, tenant_id: str, cache_key: str, value: Any, db_store_func):
        """
        Set MCP data in both caches.
        
        Args:
            connection_id: Connection ID
            tenant_id: Tenant ID
            cache_key: Cache key
            value: Value to cache
            db_store_func: Function to store in database
        """
        mcp_cache_key = TwoTierCache.get_mcp_cache_key(connection_id, tenant_id, cache_key)
        
        # Store in both caches
        _mcp_cache.set(mcp_cache_key, value)
        db_store_func(connection_id, tenant_id, cache_key, value)
        logger.debug(f"Cached MCP data in both tiers: {cache_key} for {connection_id}:{tenant_id}")
    
    @staticmethod
    def invalidate_connection(connection_id: str):
        """Invalidate connection from cache."""
        cache_key = TwoTierCache.get_connection_cache_key(connection_id)
        _connection_cache.delete(cache_key)
        logger.debug(f"Invalidated connection cache: {connection_id}")
    
    @staticmethod
    def invalidate_mcp_data(connection_id: str, tenant_id: Optional[str] = None, cache_key: Optional[str] = None):
        """
        Invalidate MCP data from cache.
        
        Args:
            connection_id: Connection ID
            tenant_id: Optional tenant ID (if None, invalidates all tenants)
            cache_key: Optional cache key (if None, invalidates all keys)
        """
        if tenant_id and cache_key:
            # Invalidate specific key
            mcp_cache_key = TwoTierCache.get_mcp_cache_key(connection_id, tenant_id, cache_key)
            _mcp_cache.delete(mcp_cache_key)
            logger.debug(f"Invalidated MCP cache: {cache_key} for {connection_id}:{tenant_id}")
        else:
            # Invalidate all keys for this connection/tenant
            # This is less efficient but needed for bulk invalidation
            keys_to_delete = []
            with _mcp_cache._lock:
                for key in list(_mcp_cache._cache.keys()):
                    if key.startswith(f"mcp:{connection_id}:"):
                        if tenant_id is None or f":{tenant_id}:" in key:
                            keys_to_delete.append(key)
            
            for key in keys_to_delete:
                _mcp_cache.delete(key)
            
            logger.debug(f"Invalidated {len(keys_to_delete)} MCP cache entries for {connection_id}:{tenant_id or 'all tenants'}")
    
    @staticmethod
    def get_cache_stats() -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "connection_cache": {
                "size": _connection_cache.size(),
                "maxsize": _connection_cache.maxsize,
                "ttl_seconds": _connection_cache.ttl_seconds
            },
            "mcp_cache": {
                "size": _mcp_cache.size(),
                "maxsize": _mcp_cache.maxsize,
                "ttl_seconds": _mcp_cache.ttl_seconds
            }
        }

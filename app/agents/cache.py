"""Simple file-based cache for MCP data."""
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Cache directory
CACHE_DIR = Path("cache")
CACHE_FILE = CACHE_DIR / "mcp_data_cache.json"


class DataCache:
    """Simple JSON file-based cache for MCP data."""
    
    def __init__(self, cache_file: Optional[Path] = None):
        self.cache_file = cache_file or CACHE_FILE
        self._ensure_cache_dir()
        self._cache: Dict[str, Any] = self._load_cache()
    
    def _ensure_cache_dir(self):
        """Ensure cache directory exists."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_cache(self) -> Dict[str, Any]:
        """Load cache from file."""
        if not self.cache_file.exists():
            logger.info(f"Cache file does not exist, creating new cache: {self.cache_file}")
            return {}
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                logger.info(f"Loaded cache from {self.cache_file} with {len(cache)} entries")
                return cache
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Error loading cache file: {e}, starting with empty cache")
            return {}
    
    def _save_cache(self):
        """Save cache to file."""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, indent=2, default=str, ensure_ascii=False)
            logger.debug(f"Cache saved to {self.cache_file}")
        except IOError as e:
            logger.error(f"Error saving cache file: {e}")
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached data by key."""
        if key in self._cache:
            logger.info(f"Cache hit for key: {key}")
            return self._cache[key]
        logger.info(f"Cache miss for key: {key}")
        return None
    
    def set(self, key: str, value: Any):
        """Set cached data for key."""
        self._cache[key] = {
            "data": value,
            "cached_at": datetime.utcnow().isoformat(),
        }
        self._save_cache()
        logger.info(f"Cached data for key: {key}")
    
    def has(self, key: str) -> bool:
        """Check if key exists in cache."""
        return key in self._cache
    
    def clear(self):
        """Clear all cached data."""
        self._cache = {}
        self._save_cache()
        logger.info("Cache cleared")
    
    def get_all_keys(self) -> list:
        """Get all cache keys."""
        return list(self._cache.keys())
    
    def invalidate(self, key: str):
        """Remove a specific key from cache."""
        if key in self._cache:
            del self._cache[key]
            self._save_cache()
            logger.info(f"Invalidated cache for key: {key}")


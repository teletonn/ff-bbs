try:
    import redis
except ImportError:
    redis = None

import json
import logging
from typing import Optional, Any, Dict, List
import os

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self, host='localhost', port=6379, db=0, password=None):
        if redis is None:
            logger.warning("Redis module not installed, using in-memory cache")
            self.redis = None
            self.memory_cache = {}
        else:
            try:
                self.redis = redis.Redis(host=host, port=port, db=db, password=password, decode_responses=True)
                self.redis.ping()  # Test connection
                logger.info("Redis cache connected successfully")
            except redis.ConnectionError:
                logger.warning("Redis not available, using in-memory cache")
                self.redis = None
                self.memory_cache = {}

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if self.redis:
            try:
                value = self.redis.get(key)
                return json.loads(value) if value else None
            except Exception as e:
                logger.error(f"Redis get error: {e}")
                return None
        else:
            return self.memory_cache.get(key)

    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Set value in cache with optional TTL in seconds."""
        try:
            json_value = json.dumps(value)
            if self.redis:
                return self.redis.set(key, json_value, ex=ttl)
            else:
                self.memory_cache[key] = value
                return True
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        try:
            if self.redis:
                return self.redis.delete(key) > 0
            else:
                return self.memory_cache.pop(key, None) is not None
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            if self.redis:
                return self.redis.exists(key) > 0
            else:
                return key in self.memory_cache
        except Exception as e:
            logger.error(f"Cache exists error: {e}")
            return False

    def get_nodes_cache_key(self) -> str:
        return "nodes:active"

    def get_routes_cache_key(self, node_id: str = None, hours: int = 24) -> str:
        if node_id:
            return f"routes:{node_id}:{hours}h"
        return f"routes:all:{hours}h"

    def get_zones_cache_key(self) -> str:
        return "zones:active"

    def get_users_cache_key(self) -> str:
        return "users:all"

# Global cache instance
cache_manager = CacheManager()

def get_cache_manager() -> CacheManager:
    return cache_manager
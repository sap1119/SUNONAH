from typing import Any, Dict, Optional
from .base_cache import BaseCache
from bolna.helpers.logger_config import configure_logger
import time
import threading

logger = configure_logger(__name__)

class InmemoryScalarCache(BaseCache):
    """An in-memory cache implementation with TTL support.
    
    This cache stores key-value pairs in memory with optional time-to-live (TTL).
    TTL can be set globally for all entries or individually per entry.
    Thread-safe operations are ensured using a lock.
    """
    
    def __init__(self, ttl: int = -1):
        """Initialize the cache.
        
        Args:
            ttl: Default time-to-live in seconds for cache entries.
                -1 means entries never expire (default)
                0 means entries expire immediately
                >0 means entries expire after specified seconds
        """
        self.data_dict: Dict[str, Any] = {}  # Main storage for cache entries
        self.ttl_dict: Dict[str, float] = {}  # Expiration timestamps
        self.ttl = ttl  # Default TTL for all entries
        self._lock = threading.Lock()  # Thread safety lock
        
    def get(self, key: str) -> Optional[Any]:
        """Retrieve a value from cache if it exists and hasn't expired.
        
        Args:
            key: The key to look up
            
        Returns:
            The cached value if found and valid, None otherwise
        """
        with self._lock:
            if key in self.data_dict:
                # No expiry if TTL is -1
                if self.ttl == -1:
                    return self.data_dict[key]
                
                # Check if entry has expired
                if time.time() < self.ttl_dict[key]:
                    return self.data_dict[key]
                else:
                    # Clean up expired entry
                    self._remove_entry(key)
            
            logger.info(f"Cache miss for key {key}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value in cache with optional TTL.
        
        Args:
            key: The key to store the value under
            value: The value to store
            ttl: Optional TTL override for this specific entry
        """
        with self._lock:
            self.data_dict[key] = value
            
            # Use entry-specific TTL if provided, otherwise use default TTL
            effective_ttl = ttl if ttl is not None else self.ttl
            if effective_ttl != -1:
                self.ttl_dict[key] = time.time() + effective_ttl
    
    def flush_cache(self, only_ephemeral: bool = True) -> None:
        """Clear the cache.
        
        Args:
            only_ephemeral: If True, only clear entries with TTL.
                          If False, clear all entries.
        """
        with self._lock:
            if only_ephemeral:
                # Only clear entries that have TTL
                keys_to_remove = [
                    key for key in list(self.data_dict.keys())
                    if key in self.ttl_dict
                ]
                for key in keys_to_remove:
                    self._remove_entry(key)
            else:
                # Clear everything
                self.data_dict.clear()
                self.ttl_dict.clear()
    
    def _remove_entry(self, key: str) -> None:
        """Remove a cache entry and its TTL info.
        
        Args:
            key: The key to remove
        
        Note: This method assumes the caller holds the lock.
        """
        self.data_dict.pop(key, None)
        self.ttl_dict.pop(key, None)
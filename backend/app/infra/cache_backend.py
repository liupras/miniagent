#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-19
# @description: A cache backend that implements the LangChain BaseStore interface and supports the LRU eviction mechanism.


from typing import List, Optional, Sequence,Tuple,Iterator
import threading
import time

from langchain_core.stores import BaseStore

class MemoryCacheStore(BaseStore[str, bytes]):
    """
    A memory-based caching backend implemented using LangChain BaseStore.
    It uses the LRU strategy from cachetools and ensures thread safety.
    """
    
    def __init__(
        self, 
        max_size: int = 1000,  # Maximum number of entries in LRU cache   
    ):
        """
        Initialize memory cache backend
        
        Args:            
            max_size: LRU cache maximum number of entries (default 1000)  
        """
        try:
            from cachetools import LRUCache
        except ImportError:
            raise ImportError("Please install cachetools: pip install cachetools")        
      
        self.max_size = max_size
        self._cache = LRUCache(maxsize=max_size)
        self._lock = threading.RLock()
        
        # Statistical information
        self._hits = 0
        self._misses = 0
        self._ttl_expirations = 0   # entries dropped due to TTL on mget_ttl

    def mget(self, keys: Sequence[str]) -> List[Optional[bytes]]:
        """Batch retrieve key-value pairs."""
        result = []
        with self._lock:
            for key in keys:
                value = self._cache.get(key)
                if value is not None:
                    self._hits += 1
                    result.append(value)
                else:
                    self._misses += 1
                    result.append(None)
        return result
    
    def mset(self, key_value_pairs: Sequence[Tuple[str, bytes]]) -> None:
        """Batch set key values."""
        with self._lock:
            for key, value in key_value_pairs:
                self._cache[key] = value
    
    def mdelete(self, keys: Sequence[str]) -> None:
        """Batch delete key."""
        with self._lock:
            for key in keys:
                if key in self._cache:
                    del self._cache[key]

    def yield_keys(self, *, prefix: Optional[str] = None) -> Iterator[str]:
        """Iterate through the keys that meet the prefix condition."""
        with self._lock:
            # Make a copy of the key to prevent dictionary modification exceptions during iteration.
            all_keys = list(self._cache.keys())
        
        for key in all_keys:
            if prefix is None or key.startswith(prefix):
                yield key   

    # ── TTL extension methods ─────────────────────────────────────────────

    def mset_with_ttl(
        self,
        key_value_pairs: Sequence[Tuple[str, bytes]],
        ttl_seconds: float,
    ) -> None:
        """Batch set key values with an expiry time.

        Entries written here will be returned as None by mget_ttl once
        ttl_seconds have elapsed.  Plain mget still returns them (no expiry
        check), so choose the right read method for your use case.

        Args:
            key_value_pairs: Sequence of (key, value_bytes) pairs.
            ttl_seconds:     Seconds until each entry is considered stale.
                             Must be positive.
        """
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be positive, got {ttl_seconds}")
        expire_at = time.monotonic() + ttl_seconds
        with self._lock:
            for key, value in key_value_pairs:
                self._cache[key] = (value, expire_at)

    def mget_ttl(self, keys: Sequence[str]) -> List[Optional[bytes]]:
        """Batch retrieve with lazy TTL expiry enforcement.

        Entries whose expiry timestamp has passed are deleted from the cache
        and returned as None.  Entries with expire_at=None (written via plain
        mset) are returned normally — they never expire.

        Args:
            keys: Keys to look up.

        Returns:
            List of value bytes or None for missing / expired entries.
        """
        result = []
        now = time.monotonic()
        keys_to_delete: List[str] = []

        with self._lock:
            for key in keys:
                entry = self._cache.get(key)
                if entry is None:
                    self._misses += 1
                    result.append(None)
                    continue

                value, expire_at = entry
                if expire_at is not None and now >= expire_at:
                    # Lazy eviction: mark for deletion, count as miss
                    keys_to_delete.append(key)
                    self._misses += 1
                    self._ttl_expirations += 1
                    result.append(None)
                else:
                    self._hits += 1
                    result.append(value)

            for key in keys_to_delete:
                if key in self._cache:
                    del self._cache[key]

        return result

    # --- Extension Methods (Management Functionality) ---

    def clear(self):
        """Clear all cache"""
        with self._lock:
            self._cache.clear()
    
    def get_stats(self) -> dict:
        """Get cache statistics, including TTL expiration count."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = f"{(self._hits / total):.2%}" if total > 0 else "0.00%"
            return {
                "backend":         "memory_lru_basestore",
                "max_size":        self.max_size,
                "current_size":    len(self._cache),
                "hits":            self._hits,
                "misses":          self._misses,
                "hit_rate":        hit_rate,
                "ttl_expirations": self._ttl_expirations,
            }

def create_cache_backend(backend_type: str = "memory", **kwargs) -> BaseStore:
    """
    Create cache backend factory function
    
    Args:
        backend_type: Cache type "memory" or "redis" (future support)
        **kwargs: Backend-specific parameters
        
    Returns:
        CacheBackend instance
    """
    if backend_type == "memory":
        return MemoryCacheStore(**kwargs)
    elif backend_type == "redis":
        # During future migrations, you can directly import LangChain's RedisStore here.
        # from langchain_community.storage import RedisStore
        # return RedisStore(redis_url=kwargs.get("url"))
        raise NotImplementedError("Redis backend will be supported soon.")
    else:
        raise ValueError(f"Unknown backend type: {backend_type}")

if __name__ == "__main__":
    import asyncio
    
    async def test_lru_cache():
        print("\n========== Testing LangChain BaseStore (LRU) ==========\n")
        
        store = MemoryCacheStore(max_size=3)
        
        # 1. Test batch write
        print("Setting keys: k1, k2, k3...")
        store.mset([("k1", b"v1"), ("k2", b"v2"), ("k3", b"v3")])
        
        # 2. Test LRU eviction
        print("Setting k4 (should evict k1)...")
        store.mset([("k4", b"v4")])
        
        # 3. Test batch read
        keys_to_test = ["k1", "k2", "k3", "k4"]
        values = store.mget(keys_to_test)
        
        for k, v in zip(keys_to_test, values):
            status = "✓" if v else "✗ (Evicted)"
            print(f"  {status} {k}: {v}")
            
        # 4. Test prefix search
        print(f"\nKeys with prefix 'k': {list(store.yield_keys(prefix='k'))}")
        
        print(f"\nFinal Stats: {store.get_stats()}")
    
    # Run test
    asyncio.run(test_lru_cache())

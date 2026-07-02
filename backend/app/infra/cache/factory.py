#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-19
# @description: Cache factory function that creates cache backend instances based on the specified type. Currently supports "memory" backend and has a placeholder for future "redis" support.

from langchain_core.stores import BaseStore
from .memory import MemoryCacheStore
from .store_registry import cache_registry

def create_cache_backend(namespace:str="default", backend_type: str = "memory", **kwargs) -> BaseStore:
    """
    Create cache backend factory function
    
    Args:
        namespace: Namespace for the cache
        backend_type: Cache type "memory" or "redis" (future support)
        **kwargs: Backend-specific parameters
        
    Returns:
        CacheBackend instance
    """
    if backend_type == "memory":
        memory_store = MemoryCacheStore(**kwargs) 
        cache_registry.register(namespace, memory_store)        
        return memory_store
    
    elif backend_type == "redis":
        # It needs to be changed to asynchronous:AsyncBaseStore.
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

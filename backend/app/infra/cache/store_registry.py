#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-02
# @description: Unified management of namespace allocation for key-value cache backends

from __future__ import annotations

from typing import Any, Dict, List, Optional
from langchain_core.stores import BaseStore

class CacheStoreRegistry:
    """
    Unified management of namespace allocation for key-value cache backends
    (MemoryCacheStore / future RedisStore).

    Each namespace must be explicitly registered with its own store instance.
    Namespaces do not share eviction budgets.
    """

    def __init__(self) -> None:
        self._stores: Dict[str, BaseStore[str, bytes]] = {}

    def register(self, namespace: str, store: BaseStore[str, bytes]) -> None:
        self._stores[namespace] = store

    def get(self, namespace: str) -> Optional[BaseStore]:
        """Use this when you are unsure whether the namespace has been registered to avoid KeyError."""
        return self._stores.get(namespace)

    # ── Management / introspection (for FastAPI admin endpoints) ──────────

    def list_namespaces(self) -> List[str]:
        return list(self._stores.keys())

    def has_namespace(self, namespace: str) -> bool:
        return namespace in self._stores

    def backend_type(self, namespace: str) -> str:
        """Return the class name of the underlying backend for the given namespace, for admin display (memory/redis, etc.)."""
        store = self._require(namespace)
        return type(store).__name__

    def get_keys(self, namespace: str, prefix: Optional[str] = None, limit: int = 100) -> List[str]:
        """
        List the keys under a given namespace.
        The limit parameter prevents loading all keys at once, which could overwhelm the backend page.
        """
        store = self._require(namespace)
        keys: List[str] = []
        for k in store.yield_keys(prefix=prefix):
            keys.append(k)
            if len(keys) >= limit:
                break
        return keys

    def get_namespace_stats(self, namespace: str) -> Dict[str, Any]:
        """
        Get statistics for a single namespace.
        """
        store = self._require(namespace)
        result: Dict[str, Any] = {
            "namespace": namespace,
            "backend_type": self.backend_type(namespace),
        }
        if hasattr(store, "get_stats"):
            backend_stats = store.get_stats()
            result["backend_stats"] = backend_stats
            result["size"] = backend_stats.get("current_size")
        else:
            keys = list(store.yield_keys())
            result["size"] = len(keys)
            result["sample_keys"] = keys[:20]
        return result

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all registered namespaces, for use with /admin/cache-store/stats."""
        return {ns: self.get_namespace_stats(ns) for ns in self.list_namespaces()}

    # ── Invalidation ────────────────────────────────────────────────────

    def delete_keys(self, namespace: str, keys: List[str]) -> int:
        """Delete the specified key and return the number of keys that actually existed and were deleted."""
        store = self._require(namespace)
        existing = [k for k in keys if store.mget([k])[0] is not None]
        if existing:
            store.mdelete(existing)
        return len(existing)

    def clear_namespace(self, namespace: str) -> int:
        """
        Clear a single namespace. 
        """
        store = self._require(namespace)
        if hasattr(store, "clear"):
            # `clear()` is not a standard interface of `BaseStore`, but an extension method of `MemoryCacheStore`;
            # If the underlying store (such as the future `RedisStore`) does not implement it, it degenerates into deleting items one by one.
            size_before = self.get_namespace_stats(namespace).get("size", 0)
            store.clear()
            return size_before
        keys = list(store.yield_keys())
        if keys:
            store.mdelete(keys)
        return len(keys)

    def clear_all(self) -> Dict[str, int]:
        """Clear all registered namespaces and return the number of keys cleared for each."""
        return {ns: self.clear_namespace(ns) for ns in self.list_namespaces()}

    def unregister(self, namespace: str) -> bool:
        """
        Unregister a namespace (remove it from the registry, but do not clear the underlying data).
        """
        return self._stores.pop(namespace, None) is not None

    # ── Internal ────────────────────────────────────────────────────────

    def _require(self, namespace: str) -> BaseStore:
        store = self._stores.get(namespace)
        if store is None:
            from app.core.i18n.i18n import t
            raise KeyError(t("cache.unregistered_namespace", namespace=namespace, all_namespaces=self.list_namespaces()))
        return store
    
# Singleton instance of CacheStoreRegistry 
cache_registry = CacheStoreRegistry()  
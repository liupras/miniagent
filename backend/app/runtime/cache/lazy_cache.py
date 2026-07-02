#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-01
# @description: LazyCache — a generic "lazy-load + single-flight + evictable" async cache.

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Dict, Generic, Hashable, Optional, TypeVar

from loguru import logger

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class AsyncLazyCache(Generic[K, V]):
    """
    A generic "lazy-load + single-flight + evictable" async cache.

    Typical Usage
    ────────
        self._pipeline_cache = AsyncLazyCache[str, WebSearchPipeline](
            builder=self._build_pipeline,
            name="web_search_pipeline",
        )
        pipeline = await self._pipeline_cache.get_or_build(tool_name, llm_provider_id)
    """

    def __init__(
        self,
        builder: Callable[..., Awaitable[V]],
        name: str = "",
        on_evict: Optional[Callable[[K, V], None]] = None,
        description: str = "",
    ) -> None:
        self._builder = builder
        self._name = name
        self._on_evict = on_evict
        self._store: Dict[K, V] = {}
        self._locks: Dict[K, asyncio.Lock] = {}
        self._description = description

    @property
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return self._description

    async def get_or_build(self, key: K, *args, **kwargs) -> V:
        if key in self._store:
            return self._store[key]

        # There is no await between in-check and assignment in a dictionary. 
        # In asyncio, which is inherently atomic in a single-threaded environment, 
        # no additional locking is needed to protect _locks itself.
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()

        async with self._locks[key]:
            if key in self._store:  # double-check
                return self._store[key]
            value = await self._builder(key, *args, **kwargs)
            self._store[key] = value
            logger.info(f"[AsyncLazyCache:{self._name}] built & cached  key={key!r}")
            return value

    def invalidate(self, key: K) -> bool:
        value = self._store.pop(key, None)
        if value is not None:
            if self._on_evict:
                self._on_evict(key, value)
            logger.info(f"[AsyncLazyCache:{self._name}] evicted  key={key!r}")
        return value is not None

    def invalidate_all(self) -> int:
        count = len(self._store)
        if self._on_evict:
            for k, v in self._store.items():
                self._on_evict(k, v)
        self._store.clear()
        logger.info(f"[AsyncLazyCache:{self._name}] all evicted  count={count}")
        return count 
    
    def invalidate_where(self, predicate: Callable[[K], bool]) -> int:
        """Batch invalidation based on predicates, returns the number of predicates that were cleared."""
        keys_to_remove = [k for k in self._store if predicate(k)]
        for k in keys_to_remove:
            self.invalidate(k)
        return len(keys_to_remove)
    
    def keys(self) -> list[K]:
        return list(self._store.keys())

    def stats(self) -> dict:
        return {"name": self._name, "size": len(self._store), "keys": self.keys(), "description": self._description}
    
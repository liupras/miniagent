#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-19
# @description: VectorStore Registry

from typing import Dict

from loguru import logger

from app.retrieval.vector_store import VectorStoreManager
from app.core.config import settings

from app.runtime.cache.lazy_cache import AsyncLazyCache
from app.schemas.common import NotFoundError

class KBNotFoundError(NotFoundError):
    def __init__(self, kb_id: int):
        super().__init__("KB", kb_id)


class VectorStoreRegistry:
    """
    Lazy cache of per-KB VectorStoreManager instances.
    """

    def __init__(self, container):
        from app.core.service_container import ServiceContainer
        if not isinstance(container, ServiceContainer):
            raise TypeError(f"Expected ServiceContainer, got {type(container)}")

        from app.runtime.cache.models import CacheType, CACHE_META
        self._stores: AsyncLazyCache = AsyncLazyCache(
            builder=self._build_store,
            name=CacheType.VECTOR_STORE_MANAGER,
            description=f"{CACHE_META[CacheType.VECTOR_STORE_MANAGER].key_name}  → {CACHE_META[CacheType.VECTOR_STORE_MANAGER].value_name}",
        )
        container.cache_registry.register(
            self._stores.name,
            self._stores,
            #key_codec=lambda raw: raw,  # kb_id is a plain int
        )

        self.kb_db   = container.kb_db
        self.embed_db = container.embed_db

    async def get(self, kb_id: int) -> "VectorStoreManager":
        """
        Return the VectorStoreManager for *kb_id*, creating it if necessary.
        """
        return await self._stores.get_or_build(kb_id)
    
    async def _build_store(self, kb_id: int) -> "VectorStoreManager":
        """
        AsyncLazyCache builder. `kb_id` is injected automatically as the
        cache key.
        """
        kb = await self.kb_db.get_kb(kb_id)
        if not kb:
            logger.error(f"KB {kb_id} not found in database.")
            raise KBNotFoundError(kb_id)

        embed_data = await self.embed_db.get_by_id(kb.embedding_id)
        return VectorStoreManager(
            db_path=settings.get_vector_db_path(),
            ollama_base_url=embed_data.base_url,
            embed_model=embed_data.model_name,
        )
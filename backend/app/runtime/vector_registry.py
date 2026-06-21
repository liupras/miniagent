#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-19
# @description: VectorStore Registry

from typing import Dict

from app.infra.retrieval.vector_store import VectorStoreManager
from app.core.config import settings


class VectorStoreRegistry:
    """
    Lazy cache of per-KB VectorStoreManager instances.

    Each KB has its own embedding model configuration, so a separate
    VectorStoreManager is needed per KB.  This registry creates them on first
    access and caches them for reuse.

    Usage by services
    ─────────────────
    Services call registry.get(kb_id) to resolve the VectorStoreManager for
    a specific KB.  They hold a reference to the registry (not to individual
    managers) so they can serve all KBs without being re-instantiated.
    """

    def __init__(self, container):
        from app.core.service_container import ServiceContainer
        if not isinstance(container, ServiceContainer):
            raise TypeError(f"Expected ServiceContainer, got {type(container)}")
        
        self._stores: Dict[int, VectorStoreManager] = {}
        self.kb_db   = container.kb_db
        self.embed_db = container.embed_db

    async def get(self, kb_id: int) -> VectorStoreManager:
        """
        Return the VectorStoreManager for *kb_id*, creating it if necessary.

        Raises ValueError if the KB does not exist.
        """
        if kb_id in self._stores:
            return self._stores[kb_id]

        kb = await self.kb_db.get_kb(kb_id)
        if not kb:
            raise ValueError(f"KB {kb_id} not found")

        store = await self._create_store_from_kb(kb)
        self._stores[kb_id] = store
        return store

    async def _create_store_from_kb(self, kb) -> VectorStoreManager:
        embed_data = await self.embed_db.get_by_id(kb.embedding_id)
        return VectorStoreManager(
            db_path        = settings.get_vector_db_path(),
            ollama_base_url = embed_data.base_url,
            embed_model    = embed_data.model_name,
        )

    def remove(self, kb_id: int) -> None:
        """Evict the cached VectorStoreManager for *kb_id*."""
        if kb_id in self._stores:
            del self._stores[kb_id]
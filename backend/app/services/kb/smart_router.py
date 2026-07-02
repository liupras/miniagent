#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun (Enhanced by Gemini)
# @date    : 2026-04-01
# @description: Intelligent querying of multiple knowledge bases.

import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass
from langchain_ollama import OllamaEmbeddings
from langchain_community.utils.math import cosine_similarity
from loguru import logger

from app.runtime.cache.lazy_cache import AsyncLazyCache

from .retrieval_model import ChunkResult
from .retrieval_model import KBInfo
from app.repositories.async_embedding import AsyncEmbeddingDatabase

@dataclass
class MultiKBQueryResult:
    """Aggregated result from multiple KBs."""
    query: str
    confidence: str  # high | low | empty
    warning: Optional[str]
    chunks: List[ChunkResult]

    @classmethod
    def create_empty(cls,query: str = "") -> "MultiKBQueryResult":
        """Returns a predefined empty result instance."""
        return cls(query=query, confidence="empty", 
            warning="No KB selected for query.",
            chunks=[])

@dataclass
class RouterConfig:
    selection_strategy:str = "keyword"
    fallback_to_all:bool=True
    max_kb_count:int=2
    extra_config:Optional[Dict] = None

class SmartRouter:
    """
    Smart Router for multi-KB queries.

    Features:
        1. Automatic KB selection via keyword / embedding.
        2. Concurrent query to selected KBs.
        3. Aggregation of chunks with confidence handling.
    """

    def __init__(
        self,
        container,
        router_config:RouterConfig,
        embedding_db:AsyncEmbeddingDatabase
    ):
        """
        kb_services: dict, key=kb_id, value=KBRetrievalService
        embed_model: embedding model for embedding-based selection
        selection_strategy: KB selection method
        llm_selector: async function(query) -> List[int], for LLM-based selection
        """
        from app.core.service_container import ServiceContainer
        if not isinstance(container, ServiceContainer):
            raise TypeError(f"Expected ServiceContainer, got {type(container)}")
        
        self.container = container

        self.kb_services = container.retrieval_service
        self.router_config = router_config
        self.embedding_db = embedding_db

        self._kb_embedding_cache: AsyncLazyCache = AsyncLazyCache[int, List[float]](
            builder=self._build_kb_embedding,
            name="smart_router_kb_embedding",
            description="kb_id → Embedding, Embedding vector for a KB's name/description/keywords",
        )
        container.cache_registry.register(
            self._kb_embedding_cache.name,
            self._kb_embedding_cache,            
        )

    async def _build_kb_embedding(self, kb_id: int, embedding) -> Optional[List[float]]:
        """
        AsyncLazyCache builder for the KB embedding cache.

        `kb_id` is injected automatically as the cache key; `embedding` is
        the extra arg passed through from _get_kb_embedding().
        """
        info: KBInfo = await self.kb_services.get_kb_info(kb_id=kb_id)

        text_parts = [info.name or ""]

        if info.description:
            text_parts.append(info.description)

        if info.keywords:
            if isinstance(info.keywords, list):
                text_parts.extend(info.keywords)
            elif isinstance(info.keywords, dict):
                text_parts.extend(info.keywords.values())

        kb_text = " ".join(text_parts).strip()

        if not kb_text:
            logger.debug(f"[SmartRouter] kb={kb_id} has no embeddable text — caching None")
            return None

        kb_vec = embedding.embed_query(kb_text)
        return kb_vec

    async def _get_kb_embedding(self, kb_id: int, embedding) -> Optional[List[float]]:
        return await self._kb_embedding_cache.get_or_build(kb_id, embedding)
    
    async def query(
        self,
        query: str,
        kb_ids: List[int],
        metadata_filter: Optional[Dict] = None
    ) -> MultiKBQueryResult:
        """
        Execute query with smart KB routing.
        """        
        if kb_ids is None:
            return MultiKBQueryResult.create_empty(query=query)
        
        selected_ids = await self._select_kbs(query,kb_ids)

        if not selected_ids:
            if not self.router_config.fallback_to_all:
                return MultiKBQueryResult.create_empty(query=query)
            else:
                selected_ids=kb_ids

        tasks = [
            self.kb_services.query(kb_id=kb_id, query=query, metadata_filter=metadata_filter)
            for kb_id in selected_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregation results
        all_chunks: List[ChunkResult] = []
        high_conf_count = 0
        warnings = []
        seen = set()

        for res in results:
            if isinstance(res, Exception):
                warning_msg = f"KB query failed: {res}"  
                if warning_msg not in seen: 
                    seen.add(res.warning)         
                    warnings.append(warning_msg)
                continue
            all_chunks.extend(res.chunks)
            if res.confidence == "high":
                high_conf_count += 1
            elif res.confidence == "low" and res.warning:
                if res.warning not in seen:
                    seen.add(res.warning)
                    warnings.append(res.warning)

        all_chunks.sort(key=lambda x: x.final_score, reverse=True)

        # Aggregation confidence
        if not all_chunks:
            level = "empty"
            warning = "No chunks retrieved from any KB." + (" | " + " | ".join(warnings) if warnings else "")
        elif high_conf_count >= 1:
            level = "high"
            warning = None if not warnings else " | ".join(warnings)
        else:
            level = "low"
            warning = "Some answers may be low-confidence." + (" | " + " | ".join(warnings) if warnings else "")

        return MultiKBQueryResult(
            query=query,
            confidence=level,
            warning=warning,
            chunks=all_chunks
        )
  
    async def _select_kbs(self, query: str,kb_ids:List[int]) -> List[int]:
        if self.router_config.selection_strategy == "keyword":
            return await self._select_kbs_by_keyword(query,kb_ids)
        else:
            return await self._select_kbs_by_embedding(query,kb_ids)

    async def _select_kbs_by_keyword(self, query: str,kb_ids:List[int]) -> List[int]:
        selected = []
        for kb_id in kb_ids:
            info = await self.kb_services.get_kb_info(kb_id=kb_id)
            keywords = info.keywords
            if keywords:
                if any(k.lower() in query.lower() for k in keywords):
                    selected.append(kb_id)
        return selected

    async def _select_kbs_by_embedding(self, query: str,kb_ids:List[int]) -> List[int]:

        embedding_config = self.router_config.extra_config or {}
        embedding_provider_name = embedding_config.get("embedding_provider_name",None)
        if not embedding_provider_name:
            raise ValueError("embedding_provider_name is not configured.")
        embedding_provider = await self.embedding_db.get_by_name(embedding_provider_name)
        if not embedding_provider:
            raise ValueError(f"embedding_provider:{embedding_provider_name} is not configured.")
        
        embedding  = OllamaEmbeddings(
            model=embedding_provider.model_name,
            base_url=embedding_provider.base_url,
        )

        query_vec = embedding.embed_query(query)
        scores = []

        for kb_id in kb_ids:
            kb_vec = await self._get_kb_embedding(kb_id, embedding)
            if kb_vec is None:
                continue

            # Similarity
            sim = cosine_similarity([query_vec], [kb_vec])[0][0]

            scores.append((kb_id, sim))

        if not scores:
            return []
        
        scores.sort(key=lambda x: x[1], reverse=True)

        # threshold filtering
        threshold = embedding_config.get("embedding_threshold", 0.7)
        selected = [kb_id for kb_id, sim in scores if sim >= threshold]

        if not selected:
            top_k = embedding_config.get("top_k_embedding", 2)
            selected = [kb_id for kb_id, _ in scores[:top_k]]

        # Maximum number of KB
        max_kb = self.router_config.max_kb_count
        return selected[:max_kb]
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-15
# @description: Knowledge-base retrieval service.

from typing import Optional, Any, Dict, List
from dataclasses import dataclass

from loguru import logger

from app.runtime.cache.lazy_cache import AsyncLazyCache
from app.services.kb.retrieval import RetrievalPipeline

from .retrieval_model import ChunkResult,KBInfo

from app.schemas.common import NotFoundError

class KBNotFoundError(NotFoundError):
    def __init__(self, kb_id: int):
        super().__init__("KB", kb_id)

class StrategyConfigNotFoundError(NotFoundError):
    def __init__(self, kb_id: int):
        super().__init__("Strategy_Config", kb_id)

class LLMConfigNotFoundError(NotFoundError):
    def __init__(self, kb_id: int):
        super().__init__("LLM", kb_id)

from app.core.i18n.i18n import t

# ─────────────────────────────────────────────────────────────────────────────
# Query result models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class QueryResult:
    """
    Structured return value of KBRetrievalService.query().

    Fields
    ------
    kb_id       Knowledge-base id
    query       Original query text
    confidence  Pipeline confidence level: 'high' | 'low' | 'empty'
    warning     Low-confidence warning message (None when level='high')
    chunks      Ranked list of retrieved chunks
    """
    kb_id:      int
    query:      str
    confidence: str
    warning:    Optional[str]
    chunks:     List[ChunkResult]


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────

class KBRetrievalService:
    """
    Retrieval service for a knowledge base.

    Pipeline caching
    ────────────────
    This service therefore maintains an in-memory pipeline cache keyed by
    (kb_id, config_id).  A pipeline is built once on first use and reused for
    all subsequent requests to the same KB with the same active StrategyConfig.

    metadata_filter and the pipeline cache
    ───────────────────────────────────────
    metadata_filter is a per-request parameter — it must NOT be baked into
    the cached pipeline.  It is passed only to pipeline.run(), never to
    from_config().  This means the same cached pipeline handles requests with
    different filters correctly.
    """

    def __init__(
        self,
        container
    ):
        from app.core.service_container import ServiceContainer
        if not isinstance(container, ServiceContainer):
            raise TypeError(f"Expected ServiceContainer, got {type(container)}")
        
        from app.infra.search.bm25_manager import bm25_manager
        self._container      = container
        self.kb_db           = container.kb_db
        self.doc_db          = container.doc_db
        self.pc_db           = container.pc_db
        self.chunk_db        = container.chunk_db
        self.vector_registry = container.vector_registry  # registry, not a single-KB instance
        self.bm25            = bm25_manager
        self.domain_registry = container.domain_registry
        self.domain_db = container.domain_db
        
        from app.runtime.cache.models import CacheType, CACHE_META
        self._pipeline_cache: AsyncLazyCache = AsyncLazyCache[int, RetrievalPipeline](
            builder=self._build_pipeline,
            name=CacheType.KB_RETRIEVAL_PIPELINE,
            description=f"{CACHE_META[CacheType.KB_RETRIEVAL_PIPELINE].key_name} → {CACHE_META[CacheType.KB_RETRIEVAL_PIPELINE].value_name}",
        )
        container.cache_registry.register(
            self._pipeline_cache.name,
            self._pipeline_cache,
            #key_codec=lambda raw: raw,  # kb_id is a plain int
        )

        self._kb_info_cache: AsyncLazyCache = AsyncLazyCache[int, KBInfo](
            builder=self._build_kb_info,
            name=CacheType.KB_INFO,
            description=f"{CACHE_META[CacheType.KB_INFO].key_name} → {CACHE_META[CacheType.KB_INFO].value_name}",
        )
        container.cache_registry.register(
            self._kb_info_cache.name,
            self._kb_info_cache,
            #key_codec=lambda raw: raw,
        )
        
    async def _build_pipeline(self, kb_id: int):
        """
        Build a RetrievalPipeline from the given StrategyConfig and LLM config.
        """
        # ── Active strategy ────────────────────────────────────────────
        strategy = await self.kb_db.get_active_strategy_config(kb_id)
        if strategy is None:
            logger.error(f"[KBRetrievalService.query] No active strategy for KB {kb_id}")
            raise StrategyConfigNotFoundError(kb_id)

        # ── LLM config linked to the KB ───────────────────────────────
        llm_config = await self.kb_db.get_llm_by_kb_id(kb_id)
        if llm_config is None:
            logger.error(f"[KBRetrievalService.query] No LLM config for KB {kb_id}")
            raise LLMConfigNotFoundError(kb_id)        
        
        return await RetrievalPipeline.create(
            config       = strategy,
            llm_config   = llm_config,
            container    = self._container
        )
    
    async def _build_kb_info(self, kb_id: int) -> "KBInfo":
        """AsyncLazyCache builder for the kb_info cache."""
        kb = await self.kb_db.get_kb(kb_id)
        if not kb:
            raise KBNotFoundError(kb_id)
        return KBInfo(
            name=kb.name,
            keywords=kb.keywords,
            description=kb.description,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Query
    # ─────────────────────────────────────────────────────────────────────────

    async def query(
        self,
        kb_id:           int,
        query:           str,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> QueryResult:
        """
        Execute the full retrieval pipeline for *query* against knowledge
        base *kb_id* and return a structured :class:`QueryResult`.
        """
        pipeline = await self._pipeline_cache.get_or_build(kb_id)
        state = await pipeline.run(
            query           = query,
            metadata_filter = metadata_filter,
        )

        confidence = state.confidence
        if confidence is None:
            logger.warning(f"[KBRetrievalService.query] No confidence result for kb={kb_id} query={query}")
            raise RuntimeError(t("kb.no_confidence"))

        # ── Serialise to QueryResult ───────────────────────────────────
        chunks_out: List[ChunkResult] = [
            ChunkResult(
                chunk_id       = rc.chunk_id,
                doc_id         = rc.doc_id,
                kb_id          = rc.kb_id,
                text           = rc.text,
                final_score    = round(rc.final_score, 4),
                vector_score   = round(rc.vector_score,  4) if rc.vector_score  is not None else None,
                bm25_score     = round(rc.bm25_score,    4) if rc.bm25_score    is not None else None,
                rrf_score      = round(rc.rrf_score,     4) if rc.rrf_score     is not None else None,
                rerank_score   = round(rc.rerank_score,  4) if rc.rerank_score  is not None else None,
                retrieval_path = rc.retrieval_path,
                metadata       = rc.metadata,
            )
            for rc in confidence.chunks
        ]

        return QueryResult(
            kb_id      = kb_id,
            query      = query,
            confidence = confidence.level,
            warning    = confidence.warning,
            chunks     = chunks_out,
        )
    
    async def get_kb_info(self, kb_id: int) -> "KBInfo":
        return await self._kb_info_cache.get_or_build(kb_id)
        


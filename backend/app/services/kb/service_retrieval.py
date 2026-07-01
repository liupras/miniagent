#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-15
# @description: Knowledge-base retrieval service.

from typing import Optional, Any, Dict, List
from dataclasses import dataclass

from loguru import logger

from .retrieval_model import ChunkResult,KBInfo

from app.schemas.common import NotFoundError

class KBNotFoundError(NotFoundError):
    def __init__(self, kb_id: int):
        super().__init__("KB", kb_id)

class StrategyConfigNotFoundError(NotFoundError):
    def __init__(self, kb_id: int):
        super().__init__("StrategyConfig", kb_id)

class LLMConfigNotFoundError(NotFoundError):
    def __init__(self, kb_id: int):
        super().__init__("LLM", kb_id)

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

    Cache invalidation
    ──────────────────
    Call invalidate(kb_id) whenever:
      - A new StrategyConfig version is activated for that KB.
      - The system language (SystemSettings["system_language"]) is changed.
      - Documents are added / deleted and the caller wants fresh BM25 state.

    The cache is per-instance, so KBRetrievalService must be a long-lived
    singleton (injected via ServiceContainer), NOT recreated per request.
    See kb_router.py for the correct dependency injection pattern.

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

        # Pipeline cache: (kb_id, config_id) → RetrievalPipeline
        # Keyed by config_id so that activating a new StrategyConfig version
        # automatically triggers a rebuild on the next request.
        self._pipeline_cache: Dict[tuple, Any] = {}
        self._kb_info_cache: Dict[int, KBInfo] = {}

    # ─────────────────────────────────────────────────────────────────────────
    # Pipeline cache management
    # ─────────────────────────────────────────────────────────────────────────

    def _cache_key(self, kb_id: int, config_id: str) -> tuple:
        return (kb_id, config_id)

    def _get_cached_pipeline(self, kb_id: int, config_id: str):
        """Return the cached pipeline for (kb_id, config_id), or None."""
        return self._pipeline_cache.get(self._cache_key(kb_id, config_id))

    def _set_cached_pipeline(self, kb_id: int, config_id: str, pipeline) -> None:
        self._pipeline_cache[self._cache_key(kb_id, config_id)] = pipeline
        logger.info(
            f"[KBRetrievalService] Pipeline cached: "
            f"kb={kb_id} config_id={config_id}"
        )

    def invalidate(self, kb_id: Optional[int] = None) -> None:
        """
        Evict pipeline(s) from the cache.

        Parameters
        ----------
        kb_id   When given, evict only pipelines for that KB.
                When None, evict all cached pipelines (e.g. after a global
                language change via SystemSettings).
        """
        if kb_id is None:
            count = len(self._pipeline_cache)
            self._pipeline_cache.clear()
            logger.info(f"[KBRetrievalService] Pipeline cache cleared ({count} entries)")
        else:
            keys_to_drop = [k for k in self._pipeline_cache if k[0] == kb_id]
            for k in keys_to_drop:
                del self._pipeline_cache[k]
            logger.info(
                f"[KBRetrievalService] Pipeline cache invalidated: "
                f"kb={kb_id} ({len(keys_to_drop)} entries removed)"
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Internal pipeline builder
    # ─────────────────────────────────────────────────────────────────────────

    async def _build_pipeline(self, kb_id: int, strategy, llm_config):
        """
        Build a RetrievalPipeline from the given StrategyConfig and LLM config.
        """
        from .retrieval import RetrievalPipeline  # local import avoids circular deps
        return await RetrievalPipeline.create(
            config       = strategy,
            llm_config   = llm_config,
            container    = self._container
        )

    async def _get_or_build_pipeline(self, kb_id: int, strategy, llm_config):
        """
        Return the cached pipeline for the active strategy, building it if
        necessary.

        Cache key is (kb_id, config_id).  When the admin activates a new
        StrategyConfig version, config_id changes, the old key is never hit
        again, and a fresh pipeline is built on the next request.
        """
        config_id = strategy.config_id
        pipeline  = self._get_cached_pipeline(kb_id, config_id)

        if pipeline is not None:
            logger.debug(
                f"[KBRetrievalService] Pipeline cache hit: "
                f"kb={kb_id} config_id={config_id}"
            )
            return pipeline

        logger.info(
            f"[KBRetrievalService] Pipeline cache miss — building: "
            f"kb={kb_id} config_id={config_id}"
        )
        pipeline = await self._build_pipeline(kb_id, strategy, llm_config)
        self._set_cached_pipeline(kb_id, config_id, pipeline)
        return pipeline

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

        Pipeline assembly (with caching)
        ---------------------------------
        1. Load the KB's active ``StrategyConfig`` from ``kb_db``.
        2. Load the ``LLM`` config linked to the KB.
        3. Return the cached pipeline for (kb_id, config_id), or build and
           cache a new one if this is the first request for this config.
        4. Run the pipeline, passing ``metadata_filter`` only at run time —
           never baked into the cached pipeline object.
        5. Wrap the ``RetrievalConfidence`` output as a ``QueryResult``.

        Raises
        ------
        ValueError   KB not found, no active strategy, or no LLM config.
        RuntimeError Pipeline build or execution failure.
        """
        # ── 1. Active strategy ────────────────────────────────────────────
        strategy = await self.kb_db.get_active_strategy_config(kb_id)
        if strategy is None:
            logger.error(f"[KBRetrievalService.query] No active strategy for KB {kb_id}")
            raise StrategyConfigNotFoundError(kb_id)

        # ── 2. LLM config linked to the KB ───────────────────────────────
        llm_config = await self.kb_db.get_llm_by_kb_id(kb_id)
        if llm_config is None:
            logger.error(f"[KBRetrievalService.query] No LLM config for KB {kb_id}")
            raise LLMConfigNotFoundError(kb_id)

        # ── 3. Get or build pipeline (cached) ─────────────────────────────
        try:
            pipeline = await self._get_or_build_pipeline(kb_id, strategy, llm_config)
        except Exception as exc:
            logger.exception(
                f"[KBRetrievalService.query] pipeline build failed kb={kb_id}"
            )
            raise RuntimeError(f"Pipeline build error: {exc}") from exc

        # ── 4. Run pipeline — metadata_filter is per-request ─────────────
        try:
            state = await pipeline.run(
                query           = query,
                metadata_filter = metadata_filter,
            )
        except Exception as exc:
            logger.exception(
                f"[KBRetrievalService.query] pipeline run failed "
                f"kb={kb_id} query={query!r}"
            )
            raise RuntimeError(f"Retrieval error: {exc}") from exc

        confidence = state.confidence
        if confidence is None:
            raise RuntimeError("Pipeline returned no confidence result.")

        # ── 5. Serialise to QueryResult ───────────────────────────────────
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
    
    async def get_kb_info(self,kb_id:int)->KBInfo:
        kb_info = self._kb_info_cache.get(kb_id)
        if not kb_info:
            kb = await self.kb_db.get_kb(kb_id)
            if not kb:
                raise KBNotFoundError(kb_id)
            kb_info = KBInfo(name=kb.name,
                keywords=kb.keywords,
                description=kb.description)
            self._kb_info_cache[kb_id] = kb_info
        return kb_info
        


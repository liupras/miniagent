#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-13
# @description: Smart-router retrieval service — wraps SmartRouter and
#               exposes the same query interface style as KBRetrievalService.

from typing import Dict, List, Optional

from loguru import logger

from .smart_router import MultiKBQueryResult, SmartRouter
from .retrieval_model import ChunkResult

# ─────────────────────────────────────────────────────────────────────────────
# Public result model
# ─────────────────────────────────────────────────────────────────────────────

class SmartRouterQueryResult:
    """
    Structured return value of KBSmartRouterService.query().

    Fields
    ------
    router_config_id  Router configuration id used for this query.
    query             Original query text.
    confidence        Aggregated confidence level: 'high' | 'low' | 'empty'.
    warning           Aggregated warning message (None when level='high').
    chunks            Globally ranked list of retrieved chunks.
    selected_kb_ids   KB ids actually queried after smart selection.
    """

    def __init__(
        self,
        router_config_id: str,
        query:            str,
        confidence:       str,
        warning:          Optional[str],
        chunks:           List[ChunkResult],
        selected_kb_ids:  List[int],
    ):
        self.router_config_id = router_config_id
        self.query            = query
        self.confidence       = confidence
        self.warning          = warning
        self.chunks           = chunks
        self.selected_kb_ids  = selected_kb_ids

    @classmethod
    def create_empty(cls, router_config_id: str, query: str) -> "SmartRouterQueryResult":
        """
        Create a default instance with an empty result.
        """
        return cls(
            router_config_id=router_config_id,
            query=query,
            confidence="empty",
            warning="No knowledge bases specified.",
            chunks=[],
            selected_kb_ids=[],
        )


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────

class KBSmartRouterService:
    """
    Application-level service that fronts SmartRouter.

    Design
    ------
    SmartRouter instances are created and cached inside SmartRouterFactory
    (one per router_config_id).  This service delegates all routing and
    retrieval logic to the factory-provided router and simply converts the
    result into a typed SmartRouterQueryResult.

    The service itself is stateless (no pipeline cache of its own) — caching
    lives entirely in SmartRouterFactory and KBRetrievalService.

    Lifecycle
    ---------
    Registered as a singleton in ServiceContainer and injected into the
    FastAPI router via Depends.  Never instantiate per-request.

    Cache invalidation
    ------------------
    Call invalidate(router_config_id) whenever a RouterConfig is updated in
    the DB so that the factory rebuilds the SmartRouter on the next request.
    Invalidating a KBRetrievalService pipeline (e.g. after document upload)
    is handled separately through container.retrieval_service.invalidate().
    """

    def __init__(self, container):
        from app.core.service_container import ServiceContainer
        if not isinstance(container, ServiceContainer):
            raise TypeError(f"Expected ServiceContainer, got {type(container)}")
        
        self._factory = container.router_factory

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    async def query(
        self,
        router_config_id: str,
        query:            str,
        kb_ids:           List[int],
        metadata_filter:  Optional[Dict] = None,
    ) -> SmartRouterQueryResult:
        """
        Route *query* to the most relevant knowledge bases and aggregate results.

        Parameters
        ----------
        router_config_id:
            Identifies the RouterConfig (selection strategy, thresholds, …)
            to use.  The corresponding SmartRouter is fetched from
            SmartRouterFactory (created once, then cached).
        query:
            Natural-language query string.
        kb_ids:
            Candidate knowledge-base ids.  The router selects a subset
            according to its strategy; pass an empty list to receive an
            empty result immediately.
        metadata_filter:
            Optional per-request filter forwarded to each KB's retrieval
            pipeline.  Not cached — safe to vary per request.

        Returns
        -------
        SmartRouterQueryResult
            Aggregated, globally ranked chunks with a confidence level.

        Raises
        ------
        ValueError   RouterConfig not found, or misconfigured router.
        RuntimeError Unexpected failure inside SmartRouter or a KB pipeline.
        """
        if not kb_ids:
            logger.warning(
                f"[KBSmartRouterService] Empty kb_ids — returning empty result. "
                f"router_config_id={router_config_id!r}"
            )
            return SmartRouterQueryResult.create_empty(
                router_config_id = router_config_id,
                query            = query
            )

        router: SmartRouter = await self._factory.get_router(router_config_id)

        logger.info(
            f"[KBSmartRouterService] query start — "
            f"router_config_id={router_config_id!r} "
            f"kb_ids={kb_ids} query={query!r}"
        )

        try:
            raw: MultiKBQueryResult = await router.query(
                query           = query,
                kb_ids          = kb_ids,
                metadata_filter = metadata_filter,
            )
        except Exception as exc:
            logger.exception(
                f"[KBSmartRouterService] SmartRouter.query failed — "
                f"router_config_id={router_config_id!r} query={query!r}"
            )
            raise RuntimeError(f"SmartRouter query error: {exc}") from exc

        logger.info(
            f"[KBSmartRouterService] query done — "
            f"confidence={raw.confidence!r} chunks={len(raw.chunks)} "
            f"warning={raw.warning!r}"
        )

        # Normalise ChunkResult scores (already rounded in KBRetrievalService,
        # but defensive rounding here keeps the contract consistent).
        chunks_out: List[ChunkResult] = [
            ChunkResult(
                chunk_id       = c.chunk_id,
                doc_id         = c.doc_id,
                kb_id          = c.kb_id,
                text           = c.text,
                final_score    = round(c.final_score,   4),
                vector_score   = round(c.vector_score,  4) if c.vector_score  is not None else None,
                bm25_score     = round(c.bm25_score,    4) if c.bm25_score    is not None else None,
                rrf_score      = round(c.rrf_score,     4) if c.rrf_score     is not None else None,
                rerank_score   = round(c.rerank_score,  4) if c.rerank_score  is not None else None,
                retrieval_path = c.retrieval_path,
                metadata       = c.metadata,
            )
            for c in raw.chunks
        ]

        # Derive the actually-queried kb_ids from the returned chunks so the
        # caller can see which KBs contributed (SmartRouter does not expose
        # selected_ids in its return value).
        selected_kb_ids = sorted({c.kb_id for c in chunks_out})

        return SmartRouterQueryResult(
            router_config_id = router_config_id,
            query            = query,
            confidence       = raw.confidence,
            warning          = raw.warning,
            chunks           = chunks_out,
            selected_kb_ids  = selected_kb_ids,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Cache management
    # ─────────────────────────────────────────────────────────────────────────

    def invalidate(self, router_config_id: Optional[str] = None) -> None:
        """
        Evict SmartRouter instance(s) from the factory cache.

        Parameters
        ----------
        router_config_id
            When given, evict only that router.
            When None, evict all cached routers.
        """
        if router_config_id is None:
            # SmartRouterFactory has no bulk-clear method; rebuild via private
            # cache clear.  If the factory exposes one in the future, use it.
            self._factory._cache.clear()
            logger.info("[KBSmartRouterService] All SmartRouter caches cleared.")
        else:
            self._factory.invalidate(router_config_id)
            logger.info(
                f"[KBSmartRouterService] SmartRouter cache invalidated: "
                f"router_config_id={router_config_id!r}"
            )

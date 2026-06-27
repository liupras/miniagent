#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-25
# @description: WebSearch Service — builds and caches WebSearchPipeline instances
#               from Tool+LLM config stored in the database.
#
# Design
# ──────
#  WebSearchService owns a Dict[tool_name, WebSearchPipeline] cache.
#  On first call for a tool name the service:
#    1. loads the Tool row (via AsyncToolDatabase)
#    2. parses tool.config  → WebSearchConfig fields
#    3. resolves rewrite_llm / rerank_llm references via the LLM table
#    4. builds WebSearchPipeline.from_config(cfg)
#    5. stores it in _pipeline_cache
#  Subsequent calls hit the in-memory cache directly.
#
#  Cache invalidation
#  ──────────────────
#  Call invalidate(tool_name) to evict a single pipeline (e.g. after an admin
#  updates the Tool row).  Call invalidate_all() to clear everything.

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Dict, List, Optional

from loguru import logger
from sqlalchemy import select

from app.infra.db.database import LLM, Tool
from .web_search import WebSearchPipeline, WebSearchState

if TYPE_CHECKING:
    from app.core.service_container import ServiceContainer
    
# ═══════════════════════════════════════════════════════════════════════════
# WebSearchService
# ═══════════════════════════════════════════════════════════════════════════

class WebSearchService:
    """
    Application-level service that manages WebSearchPipeline instances.

    Lifecycle
    ─────────
    The service is instantiated once in ServiceContainer and held at
    ``container.web_search_service``.  Each pipeline is lazily built on the
    first search call for a given tool_name and then cached for reuse.

    Thread / concurrency safety
    ───────────────────────────
    A per-tool asyncio.Lock prevents the "thundering herd" problem: if two
    coroutines request the same pipeline simultaneously, only one will build
    it while the other awaits the lock.
    """

    def __init__(self, container: "ServiceContainer") -> None:
        self._container = container
        self._tool_db   = container.tool_db
        self._llm_db = container.llm_db
        # pipeline cache: tool_name → WebSearchPipeline
        self._pipeline_cache: Dict[str, WebSearchPipeline] = {}
        # per-tool build locks (prevent duplicate construction under concurrency)
        self._build_locks: Dict[str, asyncio.Lock] = {}

    # ── Public API ────────────────────────────────────────────────────────

    async def search(
        self,        
        query: str,
        llm_provider_id:int=1,
        tool_name: str="web_search",
    ) -> WebSearchState:
        """
        Execute a web search using the pipeline configured for *tool_name*.

        Parameters
        ──────────
        tool_name : str
            Primary key of the Tool row whose ``config`` JSON drives the pipeline.
        query : str
            Raw user query (will be rewritten by the pipeline if enabled).

        Returns
        ───────
        WebSearchState
            Final pipeline state.  Callers typically use ``state.results`` or
            ``WebSearchPipeline.format_for_llm(state)`` for LLM injection.

        Raises
        ──────
        ValueError
            If the tool does not exist, is inactive, or has an invalid config.
        """
        pipeline = await self._get_or_build(tool_name,llm_provider_id)
        return await pipeline.run(query)

    async def format_for_llm(
        self,        
        query: str,
        llm_provider_id:int=1,
        tool_name: str="web_search",
    ) -> str:
        """Convenience wrapper: run search and return an LLM-ready context block."""
        state = await self.search(tool_name=tool_name, query=query,llm_provider_id=llm_provider_id)
        return WebSearchPipeline.format_for_llm(state)

    def invalidate(self, tool_name: str) -> None:
        """Evict the cached pipeline for *tool_name* (e.g. after a config update)."""
        removed = self._pipeline_cache.pop(tool_name, None)
        if removed:
            logger.info(f"[WebSearchService] pipeline evicted  tool={tool_name!r}")

    def invalidate_all(self) -> None:
        """Evict all cached pipelines."""
        count = len(self._pipeline_cache)
        self._pipeline_cache.clear()
        logger.info(f"[WebSearchService] all pipelines evicted  count={count}")

    def cache_info(self) -> Dict[str, Optional[dict]]:
        """
        Return cache statistics for every cached pipeline.
        Useful for health/monitoring endpoints.
        """
        return {
            name: pipeline.get_cache_stats()
            for name, pipeline in self._pipeline_cache.items()
        }

    # ── Internal helpers ──────────────────────────────────────────────────

    async def _get_or_build(self, tool_name: str,llm_provider_id:int) -> WebSearchPipeline:
        """Return cached pipeline or build (and cache) a new one."""
        if tool_name in self._pipeline_cache:
            return self._pipeline_cache[tool_name]

        # Ensure only one coroutine builds for this tool at a time
        if tool_name not in self._build_locks:
            self._build_locks[tool_name] = asyncio.Lock()

        async with self._build_locks[tool_name]:
            # Double-check after acquiring lock (another coroutine may have built it)
            if tool_name in self._pipeline_cache:
                return self._pipeline_cache[tool_name]

            pipeline = await self._build_pipeline(tool_name,llm_provider_id)
            self._pipeline_cache[tool_name] = pipeline
            logger.info(f"[WebSearchService] pipeline built and cached  tool={tool_name!r}")
            return pipeline

    async def _build_pipeline(self, tool_name: str,llm_provider_id:int) -> WebSearchPipeline:
        """Load Tool + LLM rows from DB and construct a WebSearchPipeline."""
        # ── 1. Load Tool ─────────────────────────────────────────────────
        tool: Optional[Tool] = await self._tool_db.get_by_name(tool_name)
        if tool is None:
            raise ValueError(f"Tool {tool_name!r} not found in database.")
        if not tool.is_active:
            raise ValueError(f"Tool {tool_name!r} is inactive.")

        llm_config = await self._llm_db.get(llm_id=llm_provider_id)

        from app.core.prompt_loader import prompt_loader
        query_rewrite_web_search_prompt_template = prompt_loader.get("web_search.query_rewrite")

        # ── 3. Build pipeline ────────────────────────────────────────────
        logger.debug(
            f"[WebSearchService] building pipeline  tool={tool_name!r}  "
        )
        return await WebSearchPipeline.create(tool_config=tool,llm_config=llm_config,
            query_rewrite_web_search_prompt_template = query_rewrite_web_search_prompt_template)

    async def _load_llm_map(self, llm_ids: List[int]) -> Dict[int, LLM]:
        """Bulk-fetch LLM rows by id list; returns {id: LLM}."""
        if not llm_ids:
            return {}
        async with self._tool_db.get_session() as session:
            result = await session.execute(
                select(LLM).where(LLM.id.in_(llm_ids))
            )
            rows = result.scalars().all()
        return {row.id: row for row in rows}
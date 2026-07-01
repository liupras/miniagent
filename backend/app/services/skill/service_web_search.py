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


from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

from loguru import logger
from sqlalchemy import select

from app.infra.db.database import LLM, Tool
from app.runtime.cache.lazy_cache import AsyncLazyCache
from .web_search import WebSearchPipeline, WebSearchState

if TYPE_CHECKING:
    from app.core.service_container import ServiceContainer
    
# ═══════════════════════════════════════════════════════════════════════════
# WebSearchService
# ═══════════════════════════════════════════════════════════════════════════

class WebSearchService:
    """
    Application-level service that manages WebSearchPipeline instances.

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

        self._pipeline_cache = AsyncLazyCache[str, WebSearchPipeline](
            builder=self._build_pipeline,
            name="web_search_pipeline",
            description="tool_name → WebSearchPipeline",
        )
        container.cache_registry.register(self._pipeline_cache.name, self._pipeline_cache) 
        
    async def search(
        self,        
        query: str,
        llm_provider_id:int=1,
        tool_name: str="web_search",
    ) -> WebSearchState:
        """
        Execute a web search using the pipeline configured for *tool_name*.
        """
        pipeline = await self._pipeline_cache.get_or_build(tool_name,llm_provider_id)
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
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-17
# @description: AgentFactory — builds, caches, and invalidates AgentRunner
#               instances.  Designed to be injected into ServiceContainer.

from __future__ import annotations
from typing import Any

from loguru import logger

from app.runtime.cache.lazy_cache import AsyncLazyCache
from app.runtime.tool_builder import build_tools_for_agent
from app.runtime.agent_runner import AgentRunner, build_agent_runner

from app.core.i18n.i18n import t
from app.schemas.common import NotFoundError
class AgentNotFoundError(NotFoundError):
    def __init__(self, agent_name: Any):
        super().__init__("Agent", agent_name)

class AgentFactory:
    """
    Factory + in-process cache for AgentRunner instances.

    Injected into ServiceContainer as ``container.agent_factory``.

    Usage::

        runner = await container.agent_factory.get_runner(agent_id)
        answer = await runner.invoke(query, history)
    """

    def __init__(self, container):
        """
        Args:
            container   ServiceContainer — provides router_factory and other
                        shared infrastructure.
        """
        self._container = container

        from app.runtime.cache.models import CacheType, CACHE_META
        self._cache = AsyncLazyCache[int, AgentRunner](
            builder=self._build_runner,
            name=CacheType.AGENT_RUNNER,
            description=f"{CACHE_META[CacheType.AGENT_RUNNER].key_name} → {CACHE_META[CacheType.AGENT_RUNNER].value_name}",
        )
        container.cache_registry.register(self._cache.name, self._cache)
        
        self._agent_db = container.agent_db
        self._tool_db = container.tool_db
        self._relation_db = container.agent_tool_relation_db
        self._conversation_service = container.conversation_service

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    async def get_runner(self, agent_id: int) -> AgentRunner:
        return await self._cache.get_or_build(agent_id)

    async def get_runner_by_name(self, name: str) -> AgentRunner:
        """
        Convenience method: resolve agent by name then delegate to get_runner.

        Useful in API handlers that receive the agent name from the client.
        """
        agent_orm = await self._agent_db.get_agent_by_name(name)
        if not agent_orm:
            raise AgentNotFoundError(name)
        return await self.get_runner(agent_orm.id)

    # ──────────────────────────────────────────────────────────────────────
    # Internal build pipeline
    # ──────────────────────────────────────────────────────────────────────

    async def _build_runner(self, agent_id: int) -> AgentRunner:
        """
        Full build pipeline for one AgentRunner.

        Steps
        ─────
        1. Load Agent ORM (with LLM relationship).
        2. Load AgentToolRelation rows (priority-ordered).
        3. Bulk-fetch Tool ORM records.
        4. Build LangChain tools (tool_builder handles type dispatch).
        5. Compile LangGraph graph and wrap in AgentRunner.
        """
        # ── 1. Agent record ────────────────────────────────────────────────
        agent_orm = await self._agent_db.get_agent(agent_id)
        if not agent_orm:
            raise AgentNotFoundError(agent_id)
        if not agent_orm.is_active:
            raise ValueError(t("agent.inactive", agent=agent_orm.name, id=agent_id))
        logger.debug(f"[AgentFactory] Building runner for agent '{agent_orm.name}'.")

        # ── 2. Tool relations (ordered by priority) ────────────────────────
        relations = await self._relation_db.get_relations_for_agent(agent_id)
        tool_names = [r.tool_name for r in relations]

        lc_tools = []
        if tool_names:        
            # ── 3. Bulk-fetch Tool records ─────────────────────────────────────
            tool_orm_map = await self._tool_db.get_tools_as_map(tool_names)

            # ── 4. Build LangChain tools ───────────────────────────────────────
            lc_tools = await build_tools_for_agent(
                container = self._container,
                agent_orm = agent_orm,
                agent_tool_relations = relations,
                tool_orm_map = tool_orm_map,
                router_factory = self._container.router_factory,
            )

        # ── 5. Compile and return ──────────────────────────────────────────
        runner = await build_agent_runner(
            agent_orm=agent_orm,
            tools=lc_tools,            
            chat_service=self._conversation_service
        )

        return runner

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-17
# @description: AgentFactory — builds, caches, and invalidates AgentRunner
#               instances.  Designed to be injected into ServiceContainer.

"""
Caching strategy
────────────────
Each AgentRunner is keyed by agent_id (int).  The cache holds the compiled
LangGraph graph + resolved tools, so repeated requests for the same agent
skip DB + model-binding overhead.

Cache invalidation
──────────────────
Call factory.invalidate(agent_id) whenever:
  • The Agent record is updated (system_prompt, llm_provider, …).
  • Tool records are added / removed / updated.
  • AgentToolRelation rows change.
  • A SmartRouter's RouterConfig is modified (also call router_factory.invalidate()).

A bulk invalidate() (no args) clears the entire cache — useful after
system language changes that affect all PromptLoaders.

Thread / concurrency safety
────────────────────────────
All methods are async.  The cache dict itself is not protected by a lock,
which is acceptable in a single-process asyncio server (FastAPI/Uvicorn).
If multi-process deployment is used, the cache is per-process by design
(same pattern as SmartRouterFactory and VectorStoreRegistry).
"""

from __future__ import annotations

from typing import Dict, Optional

from loguru import logger

from app.runtime.tool_builder import build_tools_for_agent
from app.runtime.agent_runner import AgentRunner, build_agent_runner
from app.infra.prompt_loader import PromptLoader, get_system_language


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
        self._cache: Dict[int, AgentRunner] = {}

        self._agent_db = container.agent_db
        self._tool_db = container.tool_db
        self._relation_db = container.agent_tool_relation_db
        self._chat_db = container.chat_db
        self._prompt_db = container.prompt_db
        self._seeting_db = container.setting_db

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    async def get_runner(self, agent_id: int) -> AgentRunner:
        """
        Return a ready AgentRunner for *agent_id*.

        On cache hit the runner is returned immediately (O(1) dict lookup).
        On cache miss the runner is built from DB data, compiled, and cached.

        Raises:
            ValueError  if agent_id does not exist or agent is inactive.
        """
        if agent_id in self._cache:
            return self._cache[agent_id]

        runner = await self._build_runner(agent_id)
        self._cache[agent_id] = runner
        return runner

    async def get_runner_by_name(self, name: str) -> AgentRunner:
        """
        Convenience method: resolve agent by name then delegate to get_runner.

        Useful in API handlers that receive the agent name from the client.
        """
        agent_orm = await self._agent_db.get_agent_by_name(name)
        if not agent_orm:
            raise ValueError(f"Agent '{name}' not found.")
        return await self.get_runner(agent_orm.id)

    def invalidate(self, agent_id: Optional[int] = None) -> None:
        """
        Evict one or all runners from the cache.

        Args:
            agent_id    If given, evict only that agent.
                        If None, clear the entire cache.
        """
        if agent_id is not None:
            evicted = self._cache.pop(agent_id, None)
            if evicted:
                logger.info(
                    f"[AgentFactory] Evicted cached runner "
                    f"for agent_id={agent_id} ('{evicted.agent_name}')."
                )
        else:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"[AgentFactory] Cleared entire agent cache ({count} runner(s)).")

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
        5. Resolve system language → create PromptLoader.
        6. Compile LangGraph graph and wrap in AgentRunner.
        """
        # ── 1. Agent record ────────────────────────────────────────────────
        agent_orm = await self._agent_db.get_agent(agent_id)
        if not agent_orm:
            raise ValueError(f"Agent id={agent_id} not found in database.")
        if not agent_orm.is_active:
            raise ValueError(f"Agent '{agent_orm.name}' (id={agent_id}) is inactive.")

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

        # ── 5. PromptLoader ────────────────────────────────────────────────
        lang = await get_system_language(setting_db=self._seeting_db, fallback="zh_CN")
        prompt_loader = await PromptLoader.create(lang=lang,db=self._prompt_db)

        # ── 6. Compile and return ──────────────────────────────────────────
        runner = await build_agent_runner(
            agent_orm=agent_orm,
            tools=lc_tools,
            prompt_loader=prompt_loader,
            chat_db=self._chat_db
        )

        return runner

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-29
# @description: Agent Service – business logic layer (no HTTP / FastAPI imports)

from typing import Any, List, Optional

from app.infra.db.database import Agent
from app.schemas.admin.agent import AgentCreate, AgentUpdate, AgentListParams, AgentOut, ToolBrief
from app.schemas.admin.llm import LLMOptionItem
from app.schemas.common import PageResult, NotFoundError
from app.schemas.admin.user import UserOptionItem

class AgentNotFoundError(NotFoundError):
    def __init__(self, entity_id: Any):
        super().__init__("Agent", entity_id)

class ToolNotFoundError(NotFoundError):
    def __init__(self, entity_id: Any):
        super().__init__("Tool", entity_id)

class AgentService:
    """
    Encapsulates all business logic for the Agent resource.
    """

    def __init__(
        self,
        container,
    ) -> None:
        
        from app.core.service_container import ServiceContainer
        if not isinstance(container, ServiceContainer):
            raise TypeError(f"Expected ServiceContainer, got {type(container)}")
        
        self._agent_db = container.agent_db
        self._user_agent_relation_db = container.user_agent_relation_db
        self._agent_tool_relation_db = container.agent_tool_relation_db
        self._tool_db = container.tool_db
        self._agent_factory = container.agent_factory

    # ──────────────────────────────────────────────
    # Read
    # ──────────────────────────────────────────────

    async def get_agent(self, agent_id: int) -> Optional[Agent]:
        """Return an Agent ORM object or raise AgentNotFoundError."""
        agent = await self._agent_db.get_agent(agent_id)
        return agent

    async def list_agents(self, params: AgentListParams) -> PageResult:
        """
        Return a paginated + filtered list of agents.
        """
        
        rows, total = await self._agent_db.list_agents_paginated(params)

        return PageResult(
            total=total,
            page=params.page,
            page_size=params.page_size,
            data=[AgentOut.model_validate(r) for r in rows],
        )

    # ──────────────────────────────────────────────
    # Create
    # ──────────────────────────────────────────────

    async def create_agent(self, payload: AgentCreate) -> AgentOut:
        """
        Persist a new Agent record.
        """
        agent = await self._agent_db.create_agent(payload.model_dump())
        created = await self._agent_db.get_agent(agent.id)
        return AgentOut.model_validate(created)

    # ──────────────────────────────────────────────
    # Update
    # ──────────────────────────────────────────────

    async def update_agent(self, agent_id: int, payload: AgentUpdate) -> AgentOut:
        """
        Apply a partial update to an existing Agent.
        Raises AgentNotFoundError / AgentNameConflictError as appropriate.
        """
        agent = await self._agent_db.update_agent(agent_id, payload.model_dump(exclude_unset=True))
        if agent is None:
            raise AgentNotFoundError(agent_id)

        updated = await self._agent_db.get_agent(agent_id)
        if self._agent_factory:
            self._agent_factory.invalidate(agent_id)
        return AgentOut.model_validate(updated)

    async def toggle_active(self, agent_id: int) -> None:
        """
        Flip the is_active flag of an agent.
        Returns the new is_active value.
        Raises AgentNotFoundError if the agent does not exist.
        """
        await self._agent_db.toggle_active(agent_id)
        if self._agent_factory:
            self._agent_factory.invalidate(agent_id)

    # ──────────────────────────────────────────────
    # Delete
    # ──────────────────────────────────────────────

    async def delete_agent(self, agent_id: int) -> None:
        """
        Delete a single agent by primary key.
        Raises AgentNotFoundError if the record does not exist.
        """
        await self._agent_db.delete_agent(agent_id)        
        if self._agent_factory:
            self._agent_factory.invalidate(agent_id)      
    
    async def batch_delete_agents(self, ids: List[int]) -> int:
        """
        Delete multiple agents by a list of primary keys.
        Returns the number of rows deleted.
        """
        result = await self._agent_db.batch_delete_agents(ids)
        if result == 0:
            raise AgentNotFoundError(ids)
        if self._agent_factory:
            self._agent_factory.invalidate()
        return result
    
    async def get_users_by_agent(self, agent_id: int) -> List[UserOptionItem]:
        users = await self._agent_db.get_agent_users(agent_id)
        return [UserOptionItem.model_validate(u) for u in users]
    
    async def get_agent_users(
        self,
        agent_id: int
    ):
        users = await self._agent_db.get_agent_users(agent_id)

        return [
            UserOptionItem(
                id=u.id,
                username=u.username,
                nickname=u.nickname
            )
            for u in users
        ]
    
    async def update_agent_users(
        self,
        agent_id: int,
        user_ids: list[int]
    ):        
        await self._user_agent_relation_db.update_agent_users(
            agent_id,
            user_ids
        )

    async def list_active_tools(self) -> List[ToolBrief]:
        tools = await self._tool_db.list_active_tools()
        return [ToolBrief.model_validate(t) for t in tools]

    async def get_agent_tools(self, agent_id: int) -> List[ToolBrief]:        
        relations = await self._agent_tool_relation_db.get_relations_for_agent(agent_id)
        tool_ids = [r.tool_id for r in relations]
        tools = await self._tool_db.get_tools_by_ids(tool_ids)
        tools_by_id = {tool.id: tool for tool in tools}
        return [
            ToolBrief.model_validate(tools_by_id[tool_id])
            for tool_id in tool_ids
            if tool_id in tools_by_id
        ]

    async def update_agent_tools(self, agent_id: int, tool_ids: list[int]) -> bool:
        unique_tool_ids = list(dict.fromkeys(tool_ids))
        tools = await self._tool_db.get_tools_by_ids(unique_tool_ids)
        found_tool_ids = {tool.id for tool in tools}
        missing_tool_ids = [
            tool_id for tool_id in unique_tool_ids if tool_id not in found_tool_ids
        ]
        if missing_tool_ids:
            raise ToolNotFoundError(missing_tool_ids)

        await self._agent_tool_relation_db.update_agent_tools(
            agent_id,
            unique_tool_ids,
        )
        if self._agent_factory:
            self._agent_factory.invalidate(agent_id)
        return True

    async def get_agent_llm(self, agent_id: int) -> Optional[LLMOptionItem]:
        llm = await self._agent_db.get_agent_llm(agent_id)
        if not llm:
            return None
        return LLMOptionItem.model_validate(llm)
    
    async def update_agent_llm(self, agent_id: int, llm_id: int) -> bool:
        agent = await self._agent_db.update_agent_llm(agent_id, llm_id)
        if agent is None:
            raise AgentNotFoundError(agent_id)
        if self._agent_factory:
            self._agent_factory.invalidate(agent_id)
        return agent is not None

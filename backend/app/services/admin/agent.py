#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-29
# @description: Agent Service – business logic layer (no HTTP / FastAPI imports)

from typing import List

from app.infra.db.database import Agent
from app.repositories.async_agent import AsyncAgentDatabase
from app.repositories.async_user_agent_relation import AsyncAgentUserRelationDatabase
from app.schemas.admin.agent import AgentCreate, AgentUpdate, AgentListParams, AgentOut
from app.schemas.common import PageResult
from app.schemas.admin.user import UserOptionItem

class AgentNotFoundError(Exception):
    """Raised when the requested agent does not exist."""
    def __init__(self, agent_id: int):
        self.agent_id = agent_id
        super().__init__(f"Agent {agent_id} not found")


class AgentNameConflictError(Exception):
    """Raised when an agent name collides with an existing record."""
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Agent with name '{name}' already exists")


class AgentService:
    """
    Encapsulates all business logic for the Agent resource.
    """

    def __init__(self, agent_db: AsyncAgentDatabase,user_agent_relation_db: AsyncAgentUserRelationDatabase) -> None:
        self._agent_db = agent_db
        self._user_agent_relation_db = user_agent_relation_db

    # ──────────────────────────────────────────────
    # Read
    # ──────────────────────────────────────────────

    async def get_agent(self, agent_id: int) -> Agent:
        """Return an Agent ORM object or raise AgentNotFoundError."""
        agent = await self._agent_db.get_agent(agent_id)
        if agent is None:
            raise AgentNotFoundError(agent_id)
        return agent

    async def list_agents(self, params: AgentListParams) -> PageResult:
        """
        Return a paginated + filtered list of agents.

        Filters applied when the corresponding param is not None:
        - name      → case-insensitive LIKE
        - llm_id    → exact match on Agent.llm_id
        - user_id   → any-of match through the user_agent_relations join table
        - is_active → exact boolean match
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
        Raises AgentNameConflictError on duplicate name.
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
        return AgentOut.model_validate(updated)

    async def toggle_active(self, agent_id: int) -> bool:
        """
        Flip the is_active flag of an agent.
        Returns the new is_active value.
        Raises AgentNotFoundError if the agent does not exist.
        """
        return await self._agent_db.toggle_active(agent_id)

    # ──────────────────────────────────────────────
    # Delete
    # ──────────────────────────────────────────────

    async def delete_agent(self, agent_id: int) -> None:
        """
        Delete a single agent by primary key.
        Raises AgentNotFoundError if the record does not exist.
        """
        result = await self._agent_db.delete_agent(agent_id)
        if not result:
            raise AgentNotFoundError(agent_id)
        
    async def batch_delete_agents(self, ids: List[int]) -> int:
        """
        Delete multiple agents by a list of primary keys.
        Returns the number of rows deleted.
        """
        return await self._agent_db.batch_delete_agents(ids)
    
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
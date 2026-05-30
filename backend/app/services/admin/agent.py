#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-29
# @description: Agent Service – business logic layer (no HTTP / FastAPI imports)

from typing import List, Optional

from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.infra.db.database import Agent, User
from app.repositories.async_agent import AsyncAgentDatabase
from app.schemas.admin.agent import AgentCreate, AgentUpdate, AgentListParams, AgentOut
from app.schemas.common import PageResult

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

    def __init__(self, db: AsyncAgentDatabase) -> None:
        self._db = db

    # ──────────────────────────────────────────────
    # Read
    # ──────────────────────────────────────────────

    async def get_agent(self, agent_id: int) -> Agent:
        """Return an Agent ORM object or raise AgentNotFoundError."""
        agent = await self._db.get_agent(agent_id)
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
        async with self._db.get_session() as session:
            stmt = (
                select(Agent)
                .options(selectinload(Agent.llm), selectinload(Agent.users))
            )

            if params.name:
                stmt = stmt.where(Agent.name.ilike(f"%{params.name}%"))
            if params.llm_id is not None:
                stmt = stmt.where(Agent.llm_id == params.llm_id)
            if params.is_active is not None:
                stmt = stmt.where(Agent.is_active == params.is_active)
            if params.user_id is not None:
                stmt = stmt.where(Agent.users.any(User.id == params.user_id))

            # total count (before pagination)
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total: int = (await session.execute(count_stmt)).scalar_one()

            # paginate
            offset = (params.page - 1) * params.page_size
            stmt = stmt.order_by(Agent.id).offset(offset).limit(params.page_size)
            rows: List[Agent] = list((await session.execute(stmt)).scalars().all())

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
        agent = Agent(**payload.model_dump())
        async with self._db.get_session() as session:
            session.add(agent)
            try:
                await session.commit()
                await session.refresh(agent)
            except IntegrityError:
                await session.rollback()
                raise AgentNameConflictError(payload.name)

        created = await self._db.get_agent(agent.id)
        return AgentOut.model_validate(created)

    # ──────────────────────────────────────────────
    # Update
    # ──────────────────────────────────────────────

    async def update_agent(self, agent_id: int, payload: AgentUpdate) -> AgentOut:
        """
        Apply a partial update to an existing Agent.
        Raises AgentNotFoundError / AgentNameConflictError as appropriate.
        """
        async with self._db.get_session() as session:
            stmt = (
                select(Agent)
                .options(selectinload(Agent.llm))
                .where(Agent.id == agent_id)
            )
            agent: Optional[Agent] = (await session.execute(stmt)).scalar_one_or_none()

            if agent is None:
                raise AgentNotFoundError(agent_id)

            for key, value in payload.model_dump(exclude_unset=True).items():
                setattr(agent, key, value)

            try:
                await session.commit()
                await session.refresh(agent)
            except IntegrityError:
                await session.rollback()
                raise AgentNameConflictError(payload.name or agent.name)

        updated = await self._db.get_agent(agent_id)
        return AgentOut.model_validate(updated)

    async def toggle_active(self, agent_id: int) -> bool:
        """
        Flip the is_active flag of an agent.
        Returns the new is_active value.
        Raises AgentNotFoundError if the agent does not exist.
        """
        async with self._db.get_session() as session:
            result = await session.execute(select(Agent).where(Agent.id == agent_id))
            agent: Optional[Agent] = result.scalar_one_or_none()

            if agent is None:
                raise AgentNotFoundError(agent_id)

            agent.is_active = not agent.is_active
            new_state = agent.is_active
            await session.commit()

        return new_state

    # ──────────────────────────────────────────────
    # Delete
    # ──────────────────────────────────────────────

    async def delete_agent(self, agent_id: int) -> None:
        """
        Delete a single agent by primary key.
        Raises AgentNotFoundError if the record does not exist.
        """
        async with self._db.get_session() as session:
            result = await session.execute(select(Agent).where(Agent.id == agent_id))
            agent: Optional[Agent] = result.scalar_one_or_none()

            if agent is None:
                raise AgentNotFoundError(agent_id)

            await session.delete(agent)
            await session.commit()

    async def batch_delete_agents(self, ids: List[int]) -> int:
        """
        Delete multiple agents by a list of primary keys.
        Returns the number of rows deleted.
        """
        async with self._db.get_session() as session:
            result = await session.execute(
                delete(Agent).where(Agent.id.in_(ids))
            )
            await session.commit()
            return result.rowcount
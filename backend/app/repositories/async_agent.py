#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-17
# @description: Agent Database Management (Asynchronous Version)

from typing import List,Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import Agent

class AsyncAgentDatabase(AsyncBaseDatabase):
    """Read/write operations for the Agent table."""

    async def get_agent(self, agent_id: int) -> Optional[Agent]:
        """Return Agent by primary key, eagerly loading LLM relationship."""
        async with self.get_session() as session:
            stmt = (
                select(Agent)
                .options(selectinload(Agent.llm))
                .where(Agent.id == agent_id)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_agent_by_name(self, name: str) -> Optional[Agent]:
        """Return Agent by unique name, eagerly loading LLM relationship."""
        async with self.get_session() as session:
            stmt = (
                select(Agent)
                .options(selectinload(Agent.llm))
                .where(Agent.name == name)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_active_agents(self) -> List[Agent]:
        """Return all active agents (is_active=True)."""
        async with self.get_session() as session:
            stmt = (
                select(Agent)
                .options(selectinload(Agent.llm))
                .where(Agent.is_active == True)  # noqa: E712
                .order_by(Agent.id)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
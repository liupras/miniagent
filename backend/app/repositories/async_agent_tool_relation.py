#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-17
# @description: AgentToolRelation Database Management (Asynchronous Version)

from typing import List

from sqlalchemy import select

from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import AgentToolRelation

class AsyncAgentToolRelationDatabase(AsyncBaseDatabase):
    """Read operations for the AgentToolRelation association table."""

    async def get_relations_for_agent(
        self, agent_id: int
    ) -> List[AgentToolRelation]:
        """
        Return all AgentToolRelation rows for *agent_id*, ordered by priority
        ascending (lower number = higher priority, consistent with the schema
        comment: "the smaller the number, the higher the priority").
        """
        async with self.get_session() as session:
            stmt = (
                select(AgentToolRelation)
                .where(AgentToolRelation.agent_id == agent_id)
                .order_by(AgentToolRelation.priority.asc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_enabled_relations_for_agent(
        self, agent_id: int
    ) -> List[AgentToolRelation]:
        """Return only enabled relations, ordered by priority."""
        async with self.get_session() as session:
            stmt = (
                select(AgentToolRelation)
                .where(
                    AgentToolRelation.agent_id == agent_id,
                    AgentToolRelation.enabled == True,  # noqa: E712
                )
                .order_by(AgentToolRelation.priority.asc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
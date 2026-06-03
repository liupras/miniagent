#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-17
# @description: AgentToolRelation Database Management (Asynchronous Version)

from typing import List

from sqlalchemy import delete, select

from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import AgentToolRelation, Tool

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
                select(AgentToolRelation, Tool.name.label("tool_name"))
                .join(Tool, Tool.id == AgentToolRelation.tool_id)
                .where(AgentToolRelation.agent_id == agent_id and Tool.is_active == True) 
                .order_by(AgentToolRelation.priority.asc())
            )
            result = await session.execute(stmt)
            relations = []
            for relation, tool_name in result.all():
                relation.tool_name = tool_name
                relations.append(relation)
            return relations

    async def update_agent_tools(self, agent_id: int, tool_ids: list[int]) -> None:
        """
        Replace an agent's tool relations.

        Priority follows the selected order from the client.
        """
        async with self.get_session() as session:
            await session.execute(
                delete(AgentToolRelation).where(
                    AgentToolRelation.agent_id == agent_id
                )
            )

            for priority, tool_id in enumerate(tool_ids):
                session.add(
                    AgentToolRelation(
                        agent_id=agent_id,
                        tool_id=tool_id,                        
                        priority=priority,
                    )
                )

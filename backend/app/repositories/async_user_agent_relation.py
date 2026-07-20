#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-02
# @description: User-Agent Relation Database Management (Asynchronous Version)

from sqlalchemy import delete, select

from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import Agent, User, UserAgentRelation

class AsyncAgentUserRelationDatabase(AsyncBaseDatabase):

    async def get_user_agents(self, user_id: int) -> list[Agent]:
        """Return active agents explicitly assigned to a user."""
        async with self.get_session() as session:
            stmt = (
                select(Agent)
                .join(
                    UserAgentRelation,
                    Agent.id == UserAgentRelation.agent_id,
                )
                .where(
                    UserAgentRelation.user_id == user_id,
                    Agent.is_active.is_(True),
                )
                .order_by(Agent.name.asc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def user_has_agent(self, user_id: int, agent_id: int) -> bool:
        """Check whether a user is allowed to use an active agent."""
        async with self.get_session() as session:
            stmt = (
                select(UserAgentRelation.id)
                .join(Agent, Agent.id == UserAgentRelation.agent_id)
                .where(
                    UserAgentRelation.user_id == user_id,
                    UserAgentRelation.agent_id == agent_id,
                    Agent.is_active.is_(True),
                )
            )
            return (await session.execute(stmt)).scalar_one_or_none() is not None

    async def get_agent_users(
        self,
        agent_id: int
    ) -> list[User]:
        async with self.get_session() as session:

            stmt = (
                select(User)
                .join(
                    UserAgentRelation,
                    User.id == UserAgentRelation.user_id
                )
                .where(
                    UserAgentRelation.agent_id == agent_id
                )
            )

            result = await session.execute(stmt)

            return result.scalars().all()
    
    async def update_agent_users(
        self,
        agent_id: int,
        user_ids: list[int]
    ):
        async with self.get_session() as session:            

            await session.execute(
                delete(UserAgentRelation).where(
                    UserAgentRelation.agent_id == agent_id
                )
            )

            for user_id in user_ids:
                session.add(
                    UserAgentRelation(
                        agent_id=agent_id,
                        user_id=user_id
                    )
                )


#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-02
# @description: User-Agent Relation Database Management (Asynchronous Version)

from sqlalchemy import delete, select

from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import User, UserAgentRelation

class AsyncAgentUserRelationDatabase(AsyncBaseDatabase):

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

            
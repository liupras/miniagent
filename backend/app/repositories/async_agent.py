#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-17
# @description: Agent Database Management (Asynchronous Version)

from typing import List,Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import selectinload

from app.schemas.admin.agent import AgentListParams
from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import LLM, Agent, User

class AsyncAgentDatabase(AsyncBaseDatabase):
    """Read/write operations for the Agent table."""

    async def get_agent(self, agent_id: int) -> Optional[Agent]:
        """Return Agent by primary key, eagerly loading LLM relationship."""
        async with self.get_session() as session:
            stmt = (
                select(Agent)
                .options(selectinload(Agent.llm))
                .options(selectinload(Agent.users))
                .where(Agent.id == agent_id)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        
    async def get_agent_users(self, agent_id: int):
        async with self.get_session() as session:            
            stmt = (
                select(User.id, User.username, User.nickname)
                .join(User.agents)
                .where(Agent.id == agent_id)
            )
            result = await session.execute(stmt)            
            return result.all()

    async def list_agents_paginated(self, params: AgentListParams):
        async with self.get_session() as session:
            stmt = (
                select(Agent)
                .options(
                    selectinload(Agent.llm), 
                    selectinload(Agent.users),
                    #selectinload(Agent.tools.and_(Tool.is_active == True))
                )
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
            rows: List[Agent] = list((await session.execute(stmt)).scalars().unique().all())

            return rows, total
    
    async def create_agent(self, agent_data: dict) -> Agent:

        agent = Agent(**agent_data)
        async with self.get_session() as session:
            session.add(agent)            
            return agent
        
    async def update_agent(self, agent_id: int, update_data: dict) -> Agent|None:

        async with self.get_session() as session:
            stmt = select(Agent).options(selectinload(Agent.llm)).where(Agent.id == agent_id)
            result = await session.execute(stmt)
            agent = result.scalar_one_or_none()

            if agent is None:
                return None
            
            for key, value in update_data.items():
                setattr(agent, key, value)
  
            return agent

    async def toggle_active(self, agent_id: int) -> None:
        async with self.get_session() as session:
            await session.execute(
                update(Agent)
                .where(Agent.id == agent_id)
                .values(is_active=~Agent.is_active)
            ) 
    
    async def delete_agent(self, agent_id: int) -> int:
        async with self.get_session() as session:
            result = await session.execute(
                delete(Agent).where(Agent.id == agent_id)
            )        
            return result.rowcount    
 
    async def batch_delete_agents(self, ids: List[int]) -> int:
        """
        Delete multiple agents by a list of primary keys.
        Returns the number of rows deleted.
        """
        async with self.get_session() as session:
            result = await session.execute(
                delete(Agent).where(Agent.id.in_(ids))
            )
            return result.rowcount
        
    async def get_agent_llm(self, agent_id: int) -> Optional[LLM]:

        async with self.get_session() as session:
            stmt = select(Agent).options(selectinload(Agent.llm)).where(Agent.id == agent_id)
            result = await session.execute(stmt)
            agent = result.scalar_one_or_none()
            
            if not agent:
                return None
                
            return agent.llm
        
    async def update_agent_llm(self, agent_id: int, llm_id: int) -> None:

        async with self.get_session() as session:
            agent = await session.get(Agent, agent_id)
            if not agent:
                return None            

            agent.llm_id = llm_id

            return agent
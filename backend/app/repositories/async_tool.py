#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-17
# @description: Tool Database Management (Asynchronous Version)

from typing import List,Optional,Dict

from sqlalchemy import select

from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import Tool

class AsyncToolDatabase(AsyncBaseDatabase):
    """Read operations for the Tool table."""

    async def get_tool(self, tool_name: str) -> Optional[Tool]:
        """Return Tool by primary key (name)."""
        async with self.get_session() as session:
            stmt = select(Tool).where(Tool.name == tool_name)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_tool_by_id(self, tool_id: int) -> Optional[Tool]:
        """Return Tool by primary key."""
        async with self.get_session() as session:
            stmt = select(Tool).where(Tool.id == tool_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_tools_by_names(self, names: List[str]) -> List[Tool]:
        """Bulk-fetch Tools by name list. Preserves DB ordering."""
        if not names:
            return []
        async with self.get_session() as session:
            stmt = select(Tool).where(Tool.name.in_(names))
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_tools_by_ids(self, ids: List[int]) -> List[Tool]:
        """Bulk-fetch Tools by id list."""
        if not ids:
            return []
        async with self.get_session() as session:
            stmt = select(Tool).where(Tool.id.in_(ids))
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_active_tools(self) -> List[Tool]:
        """Return all active tools."""
        async with self.get_session() as session:
            stmt = (
                select(Tool)
                .where(Tool.is_active == True)
                .order_by(Tool.tool_type.asc(), Tool.name.asc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_tools_as_map(self, names: List[str]) -> Dict[str, Tool]:
        """
        Return {tool_name: Tool ORM} for the given names.
        Convenient for the tool-builder look-up pattern.
        """
        tools = await self.get_tools_by_names(names)
        return {t.name: t for t in tools}

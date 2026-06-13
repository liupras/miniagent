#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-17
# @description: Tool Database Management (Asynchronous Version)

from typing import Any, Dict, List, Optional
from sqlalchemy import delete, func, select, update

from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import Tool

class AsyncToolDatabase(AsyncBaseDatabase):
    """Read operations for the Tool table."""

    async def get_by_name(self, tool_name: str) -> Optional[Tool]:
        """Return Tool by primary key (name)."""
        async with self.get_session() as session:
            stmt = select(Tool).where(Tool.name == tool_name)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_by_id(self, tool_id: int) -> Optional[Tool]:
        """Return Tool by primary key."""
        async with self.get_session() as session:
            stmt = select(Tool).where(Tool.id == tool_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        
    async def fetch_list(
        self,            
        page: int = 1,
        page_size: int = 20,
        tool_type: str | None = None,
        is_active: bool | None = None,
        keyword: str | None = None,
    ) -> tuple[int, list[Tool]]:
        
        async with self.get_session() as session:
            stmt = select(Tool)
            count_stmt = select(func.count()).select_from(Tool)

            if tool_type is not None:
                stmt = stmt.where(Tool.tool_type == tool_type)
                count_stmt = count_stmt.where(Tool.tool_type == tool_type)

            if is_active is not None:
                stmt = stmt.where(Tool.is_active == is_active)
                count_stmt = count_stmt.where(Tool.is_active == is_active)

            if keyword:
                like = f"%{keyword}%"
                condition = Tool.name.ilike(like) | Tool.description.ilike(like)
                stmt = stmt.where(condition)
                count_stmt = count_stmt.where(condition)

            total: int = (await session.execute(count_stmt)).scalar_one()

            stmt = (
                stmt.order_by(Tool.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            items = list((await session.execute(stmt)).scalars().all())
            return total, items
        
    async def fetch_stats(self) -> dict[str, Any]:
        
        async with self.get_session() as session:
            total = (
                await session.execute(select(func.count()).select_from(Tool))
            ).scalar_one()

            active = (
                await session.execute(
                    select(func.count()).select_from(Tool).where(Tool.is_active == True)  # noqa: E712
                )
            ).scalar_one()

            type_rows = (
                await session.execute(
                    select(Tool.tool_type, func.count().label("cnt")).group_by(Tool.tool_type)
                )
            ).all()

            return {
                "total": total,
                "active": active,
                "by_type": {row.tool_type: row.cnt for row in type_rows},
            }

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
    
    async def insert(self, data: dict[str, Any]) -> Tool:
        
        async with self.get_session() as session:
            tool = Tool(**data)
            session.add(tool)
            return tool

    async def update_fields(
        self, tool_id: int, data: dict[str, Any]
    ) -> Tool:
        
        async with self.get_session() as session:
            stmt = select(Tool).where(Tool.id == tool_id)
            result = await session.execute(stmt)
            tool = result.scalar_one_or_none()

            if not tool:
                return None
            for field, value in data.items():
                setattr(tool, field, value)

            return tool

    async def delete_tool(self,  tool_id: int) -> int:
        async with self.get_session() as session:
            result = await session.execute(
                delete(Tool).where(Tool.id == tool_id)
            )
            return result.rowcount

    async def bulk_delete_tools(
        self, tool_ids: list[int]
    ) -> int:
        
        async with self.get_session() as session:
            deleted = 0
            for tid in tool_ids:
                tool = await self.get_by_id(tid)
                if tool is not None:
                    await session.delete(tool)
                    deleted += 1
            return deleted

    async def toggle_active(self, tool_id: int) -> None:
        async with self.get_session() as session:
            await session.execute(
                update(Tool)
                .where(Tool.id == tool_id)
                .values(is_active=~Tool.is_active)
            )
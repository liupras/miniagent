#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-03
# @description: Tool Service – business logic layer (no HTTP / FastAPI imports)

from __future__ import annotations

from typing import Any

from app.infra.db.database import Tool
from app.schemas.admin.tool import ToolCreate, ToolUpdate
from app.schemas.common import create_exception_pair

ToolNotFoundError, ToolAlreadyExistsError = create_exception_pair("Tool")

class ToolService:

    def __init__(self, container) -> None:
        from app.core.service_container import ServiceContainer
        if not isinstance(container, ServiceContainer):
            raise TypeError(f"Expected ServiceContainer, got {type(container)}")
        
        self._db = container.tool_db
        self._agent_factory = container.agent_factory

    async def get(self, tool_id: int) -> Tool | None:
        tool = await self._db.get_by_id(tool_id)
        return tool

    async def get_by_name(self, name: str) -> Tool | None:
        return await self._db.get_by_name(name)

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        tool_type: str | None = None,
        is_active: bool | None = None,
        keyword: str | None = None,
    ) -> tuple[int, list[Tool]]:
        result = await self._db.fetch_list(
            page=page,
            page_size=page_size,
            tool_type=tool_type,
            is_active=is_active,
            keyword=keyword,
        )
        return result

    async def stats(self) -> dict[str, Any]:
        return await self._db.fetch_stats()

    async def create(self, payload: ToolCreate) -> Tool:
        if await self._db.get_by_name(payload.name):
            raise ToolAlreadyExistsError(payload.name)
        return await self._db.insert(payload.model_dump())

    async def update(self, tool_id: int, payload: ToolUpdate) -> Tool | None:
        tool = await self._db.get_by_id(tool_id)
        if tool is None:
            raise ToolNotFoundError(tool_id)
        data = payload.model_dump(exclude_unset=True)
        if "name" in data and data["name"] != tool.name:
            if await self._db.get_by_name(data["name"]):
                raise ToolAlreadyExistsError(data["name"])

        tool = await self._db.update_fields(tool_id, data)
        if tool is None:
            raise ToolNotFoundError(tool_id)
        if self._agent_factory:
            self._agent_factory.invalidate()
        return tool

    async def toggle_active(self, tool_id: int) -> None:        
        await self._db.toggle_active(tool_id)
        if self._agent_factory:
            self._agent_factory.invalidate()

    async def delete(self, tool_id: int) -> None:
        await self._db.delete_tool(tool_id)
        if self._agent_factory:
            self._agent_factory.invalidate()

    async def bulk_delete(self, tool_ids: list[int]) -> int:
        count = await self._db.bulk_delete_tools(tool_ids)
        if self._agent_factory:
            self._agent_factory.invalidate()
        return count

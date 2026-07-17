#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-03
# @description: Tool Service – business logic layer (no HTTP / FastAPI imports)

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.service_container import ServiceContainer

from app.infra.db.database import Tool
from app.schemas.admin.tool import ToolCreate, ToolRead, ToolUpdate
from app.schemas.common import NotFoundError,AlreadyExistsError

class ToolNotFoundError(NotFoundError):
    def __init__(self, entity_id: Any):
        super().__init__("Tool", entity_id)

class ToolAlreadyExistsError(AlreadyExistsError):
    def __init__(self, entity_id: Any):
        super().__init__("Tool", entity_id)

class ToolService:

    def __init__(self, container:ServiceContainer) -> None:
        
        self._db = container.tool_db
        self._cache = container.object_cache_invalidator

    async def get(self, tool_id: int) -> Tool | None:
        tool = await self._db.get_by_id(tool_id)
        if not tool:
            raise ToolNotFoundError(tool_id)
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
        db_tool = await self._db.insert(payload.model_dump())
        return ToolRead.model_validate(db_tool)

    async def update(self, tool_id: int, payload: ToolUpdate) -> Tool | None:
        db_tool = await self._db.get_by_id(tool_id)
        if db_tool is None:
            raise ToolNotFoundError(tool_id)
        data = payload.model_dump(exclude_unset=True)
        if "name" in data and data["name"] != db_tool.name:
            if await self._db.get_by_name(data["name"]):
                raise ToolAlreadyExistsError(data["name"])

        db_tool = await self._db.update_fields(tool_id, data)
        if db_tool is None:
            raise ToolNotFoundError(tool_id)
        self._cache.on_tool_changed()
        return ToolRead.model_validate(db_tool)

    async def toggle_active(self, tool_id: int) -> None:        
        await self._db.toggle_active(tool_id)
        self._cache.on_tool_changed()

    async def delete(self, tool_id: int) -> int:
        deleted = await self._db.delete_tool(tool_id)
        if not deleted:
            raise ToolNotFoundError(tool_id)
        self._cache.on_tool_changed()
        return deleted

    async def bulk_delete(self, tool_ids: list[int]) -> int:
        count = await self._db.bulk_delete_tools(tool_ids)
        self._cache.on_tool_changed()
        return count

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-11
# @description: Strategy Config Service

from __future__ import annotations
from typing import Any

from app.schemas.admin.strategy_config import (
    StrategyConfigCreate,
    StrategyConfigListOut,
    StrategyConfigOut,
    StrategyConfigUpdate,
)
from app.schemas.common import NotFoundError,BadRequestError

class StrategyConfigNotFoundError(NotFoundError):
    def __init__(self, entity_id: Any):
        super().__init__("StrategyConfig", entity_id)

class StrategyConfigBadRequestError(BadRequestError):
    def __init__(self, entity_id: Any):
        super().__init__("StrategyConfig", entity_id)
        
class StrategyConfigService:
    """Business logic for StrategyConfig."""

    def __init__(self, container):
        from app.core.service_container import ServiceContainer
        if not isinstance(container, ServiceContainer):
            raise TypeError(f"Expected ServiceContainer, got {type(container)}")
        
        self._db = container.strategy_config_db
        self._retrieval_service = container.retrieval_service

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_or_404(self, config_id: str) -> StrategyConfigOut:
        obj = await self._db.get_by_id(config_id)
        if obj is None:
            raise StrategyConfigNotFoundError(config_id)
        return StrategyConfigOut.model_validate(obj)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def list_all(
        self,
        page: int = 1,
        page_size: int = 20,
        kb_id: int | None = None,
        is_active: bool | None = None
    ) -> StrategyConfigListOut:
        """List all strategy configs with optional filters."""
        total, items = await self._db.list_all(
            page=page,
            page_size=page_size,
            kb_id=kb_id,
            is_active=is_active
        )
        return StrategyConfigListOut(total=total, page=page, page_size=page_size, items=[StrategyConfigOut.model_validate(item) for item in items])

    async def create(self, payload: StrategyConfigCreate) -> StrategyConfigOut:
        data = payload.model_dump()
        obj = await self._db.create(data)
        return StrategyConfigOut.model_validate(obj)

    async def get(self, config_id: str) -> StrategyConfigOut:
        return await self._get_or_404(config_id)

    async def get_active(self, kb_id: int) -> StrategyConfigOut:
        obj = await self._db.get_active_by_kb(kb_id)
        if obj is None:
            raise StrategyConfigNotFoundError(kb_id)
        return StrategyConfigOut.model_validate(obj)

    async def list(
        self, kb_id: int, page: int = 1, page_size: int = 20
    ) -> StrategyConfigListOut:
        total, items = await self._db.list_by_kb(kb_id, page, page_size)
        return StrategyConfigListOut(
            total=total,
            items=[StrategyConfigOut.model_validate(i) for i in items],
        )

    async def update(self, config_id: str, payload: StrategyConfigUpdate) -> StrategyConfigOut:
        data = payload.model_dump(exclude_none=True)
        if not data:
            raise StrategyConfigBadRequestError(config_id)
        
        obj = await self._get_or_404(config_id)
        if not obj:
            raise StrategyConfigNotFoundError(config_id)
        if not self._retrieval_service:
            self._retrieval_service.invalidate(kb_id=obj.kb_id)
        await self._db.update(config_id,data)
        return await self._get_or_404(config_id)

    async def delete(self, config_id: str) -> int:
        kb_id = await self._db.delete(config_id)
        if not self._retrieval_service:
            self._retrieval_service.invalidate(kb_id=kb_id)
        return kb_id

    # ------------------------------------------------------------------
    # Activate
    # ------------------------------------------------------------------

    async def activate(self, config_id: str) -> StrategyConfigOut:
        obj = await self._get_or_404(config_id)
        rows = await self._db.activate(config_id, obj.kb_id)
        if rows == 0:
            raise StrategyConfigNotFoundError(config_id)
        if not self._retrieval_service:
            self._retrieval_service.invalidate(kb_id=obj.kb_id)
        return await self._get_or_404(config_id)

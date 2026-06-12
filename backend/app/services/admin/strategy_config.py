#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-11
# @description: Strategy Config Service

from __future__ import annotations

from fastapi import HTTPException, status

from app.repositories.async_strategy_config import AsyncStrategyConfigDatabase
from app.schemas.admin.strategy_config import (
    StrategyConfigCreate,
    StrategyConfigListOut,
    StrategyConfigOut,
    StrategyConfigUpdate,
)
from app.schemas.common import create_exception_pair

StrategyConfigNotFoundError, StrategyConfigAlreadyExistsError = create_exception_pair("StrategyConfig")

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
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided for update.",
            )
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
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Activation failed.",
            )
        if not self._retrieval_service:
            self._retrieval_service.invalidate(kb_id=obj.kb_id)
        return await self._get_or_404(config_id)

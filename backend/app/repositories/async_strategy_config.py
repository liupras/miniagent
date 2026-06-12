#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-11
# @description: RouterConfig Database Management

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update, delete, func

from app.infra.db.async_base import AsyncBaseDatabase
from app.infra.db.database import StrategyConfig

class AsyncStrategyConfigDatabase(AsyncBaseDatabase):
    """Database operations for StrategyConfig."""

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_id(self, config_id: str) -> StrategyConfig | None:
        async with self.get_session() as session:
            result = await session.execute(
                select(StrategyConfig).where(StrategyConfig.config_id == config_id)
            )
            return result.scalar_one_or_none()

    async def get_active_by_kb(self, kb_id: int) -> StrategyConfig | None:
        async with self.get_session() as session:
            result = await session.execute(
                select(StrategyConfig).where(
                    StrategyConfig.kb_id == kb_id,
                    StrategyConfig.is_active.is_(True),
                )
            )
            return result.scalar_one_or_none()

    async def list_by_kb(
        self,
        kb_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[int, list[StrategyConfig]]:
        async with self.get_session() as session:
            base_q = select(StrategyConfig).where(StrategyConfig.kb_id == kb_id)

            total_result = await session.execute(
                select(func.count()).select_from(base_q.subquery())
            )
            total: int = total_result.scalar_one()

            rows_result = await session.execute(
                base_q.order_by(StrategyConfig.version.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            items = list(rows_result.scalars().all())
            return total, items
        
    async def list_all(
        self,
        page: int = 1,
        page_size: int = 20,
        kb_id: int | None = None,
        is_active: bool | None = None
    ) -> tuple[int, list[StrategyConfig]]:
        """List all strategy configs with optional filters."""
        async with self.get_session() as session:
            base_q = select(StrategyConfig)
            
            if kb_id is not None:
                base_q = base_q.where(StrategyConfig.kb_id == kb_id)
            if is_active is not None:
                base_q = base_q.where(StrategyConfig.is_active == is_active)
            
            total_result = await session.execute(
                select(func.count()).select_from(base_q.subquery())
            )
            total: int = total_result.scalar_one()

            rows_result = await session.execute(
                base_q.order_by(StrategyConfig.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            items = list(rows_result.scalars().all())
            return total, items

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create(self, data: dict[str, Any]) -> StrategyConfig:
        async with self.get_session() as session:
            obj = StrategyConfig(**data)
            session.add(obj)
            return obj

    async def update(self, config_id: str, data: dict[str, Any]) -> int:
        async with self.get_session() as session:
            update_result = await session.execute(
                update(StrategyConfig)
                .where(StrategyConfig.config_id == config_id)
                .values(**data)
            )
            return update_result.rowcount

    async def delete(self, config_id: str) -> int:
        """To facilitate cache refresh, return kb_id"""        
        async with self.get_session() as session:
            result = await session.execute(
                select(StrategyConfig.kb_id).where(StrategyConfig.config_id == config_id)
            )
            kb_id = result.scalar_one_or_none()
            
            if kb_id is None:
                return 0  # Record does not exist
            
            delete_result = await session.execute(
                delete(StrategyConfig).where(StrategyConfig.config_id == config_id)
            )
            return kb_id

    # ------------------------------------------------------------------
    # Activate helpers
    # ------------------------------------------------------------------

    async def deactivate_all_for_kb(self, kb_id: int) -> int:
        """Set is_active=False for every config belonging to kb_id."""
        async with self.get_session() as session:
            result = await session.execute(
                update(StrategyConfig)
                .where(StrategyConfig.kb_id == kb_id)
                .values(is_active=False)
            )
            return result.rowcount

    async def activate(self, config_id: str, kb_id: int) -> int:
        """Atomically deactivate all siblings, then activate the target."""
        async with self.get_session() as session:
            await session.execute(
                update(StrategyConfig)
                .where(StrategyConfig.kb_id == kb_id)
                .values(is_active=False)
            )
            result = await session.execute(
                update(StrategyConfig)
                .where(StrategyConfig.config_id == config_id)
                .values(is_active=True)
            )
            return result.rowcount

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Gemini (Modified from Liu Lijun)
# @date    : 2026-04-15
# @description: RouterConfig Database Management (Asynchronous Version)

import uuid
from datetime import datetime
from typing import Optional, Dict, List, Any

from sqlalchemy import select
from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import RouterConfig


class AsyncRouterConfigDatabase(AsyncBaseDatabase):

    async def create_config(
        self,
        selection_strategy: str = "embedding",
        fallback_to_all: bool = True,
        allow_multi_kb: bool = True,
        max_kb_count: int = 3,
        extra_config: Optional[Dict] = None,
        config_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Creates a route configuration and returns config_id; 
        returns None if config_id already exists.
        """
        async with self.get_session() as session:
            cid = config_id or str(uuid.uuid4())

            existing = await session.get(RouterConfig, cid)
            if existing:
                return None

            config = RouterConfig(
                config_id=cid,
                selection_strategy=selection_strategy,
                fallback_to_all=fallback_to_all,
                allow_multi_kb=allow_multi_kb,
                max_kb_count=max_kb_count,
                extra_config=extra_config,
                created_at=datetime.now(),
            )
            session.add(config)
            # `flush` ensures data is entered into the database session; 
            # `commit` is handled by the base class `get_session`.
            await session.flush()
            return cid

    async def get_config(self, config_id: str) -> Optional[RouterConfig]:

        async with self.get_session() as session:
            config = await session.get(RouterConfig, config_id)
            return config

    async def update_config(self, config_id: str, **kwargs) -> bool:
        """
        Updates the specified field and returns a success or failure message.
        Updateable fields: selection_strategy / fallback_to_all / allow_multi_kb / max_kb_count / extra_config
        """
        allowed_fields = {
            "selection_strategy",
            "fallback_to_all",
            "allow_multi_kb",
            "max_kb_count",
            "extra_config",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return False

        async with self.get_session() as session:
            config = await session.get(RouterConfig, config_id)
            if not config:
                return False

            for field, value in updates.items():
                setattr(config, field, value)
            
            await session.flush()
            return True

    async def delete_config(self, config_id: str) -> bool:
        """Delete configuration; returns False if it does not exist."""
        async with self.get_session() as session:
            config = await session.get(RouterConfig, config_id)
            if not config:
                return False

            await session.delete(config)
            return True

    async def get_all_configs(self) -> List[Dict]:
        """
        Retrieve all configurations, sorted in descending order of creation time.
        """
        async with self.get_session() as session:
            stmt = select(RouterConfig).order_by(RouterConfig.created_at.desc())
            result = await session.execute(stmt)
            configs = result.scalars().all()
            return [self._to_dict(c) for c in configs]

    async def get_configs_by_strategy(self, strategy: str) -> List[Dict]:
        """
        Filter by selected strategy.
        """
        async with self.get_session() as session:
            stmt = (
                select(RouterConfig)
                .where(RouterConfig.selection_strategy == strategy)
                .order_by(RouterConfig.created_at.desc())
            )
            result = await session.execute(stmt)
            configs = result.scalars().all()
            return [self._to_dict(c) for c in configs]

    async def exists(self, config_id: str) -> bool:

        config = await self.get_config(config_id)
        return config is not None

    # ---------- Internal tools ----------
    @staticmethod
    def _to_dict(config: RouterConfig) -> Dict[str, Any]:
        """Convert the model object into a dictionary."""
        return {
            "config_id": config.config_id,
            "selection_strategy": config.selection_strategy,
            "fallback_to_all": config.fallback_to_all,
            "allow_multi_kb": config.allow_multi_kb,
            "max_kb_count": config.max_kb_count,
            "extra_config": config.extra_config,
            "created_at": config.created_at,
        }
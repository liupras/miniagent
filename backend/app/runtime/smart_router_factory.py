#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-19
# @description: SmartRouter Registry

from typing import Dict

from loguru import logger

from app.infra.db.database import RouterConfig
from app.runtime.cache.lazy_cache import AsyncLazyCache
from app.services.kb.smart_router import SmartRouter

from app.schemas.common import NotFoundError

class RouterConfigNotFoundError(NotFoundError):
    def __init__(self, router_config_id: str):
        super().__init__("Router_Config", router_config_id)

class SmartRouterFactory:
    """
    Manage SmartRouter instances (one per router_config_id).
    """

    def __init__(self, container):
        from app.core.service_container import ServiceContainer
        if not isinstance(container, ServiceContainer):
            raise TypeError(f"Expected ServiceContainer, got {type(container)}")
        
        self.container = container

        from app.runtime.cache.models import CacheType, CACHE_META
        self._cache: AsyncLazyCache = AsyncLazyCache[str, SmartRouter](
            builder=self._build_router,
            name=CacheType.SMART_ROUTER,
            description=f"{CACHE_META[CacheType.SMART_ROUTER].key_name} → {CACHE_META[CacheType.SMART_ROUTER].value_name}",
        )
        container.cache_registry.register(
            self._cache.name,
            self._cache,
        )  


    async def _build_router(self, router_config_id: str) -> SmartRouter:
        """
        Build a SmartRouter from the given RouterConfig.
        """
        # 1. Load RouterConfig from DB
        router_config_orm = await self.container.router_config_db.get_by_id(router_config_id)
        if not router_config_orm:
            logger.error(f"RouterConfig {router_config_id} not found in DB")
            raise RouterConfigNotFoundError(router_config_id)

        # 2. Convert to dataclass
        router_config = RouterConfig(
            selection_strategy = router_config_orm.selection_strategy,
            fallback_to_all    = router_config_orm.fallback_to_all,
            max_kb_count       = router_config_orm.max_kb_count,
            extra_config       = router_config_orm.extra_config,
        )

        # 3. Building SmartRouter
        router = SmartRouter(
            container = self.container,
            router_config= router_config,
            embedding_db = self.container.embed_db,
        )

        return router

    async def get_router(self, router_config_id: str) -> SmartRouter:
        return await self._cache.get_or_build(router_config_id)

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-08
# @description: Router Config Service

from app.schemas.common import create_exception_pair
from app.schemas.admin.router_config import RouterConfigResponse, RouterConfigUpdate

RouterConfigNotFoundError, RouterConfigAlreadyExistsError = create_exception_pair("RouterConfig")

class RouterConfigService:

    def __init__(self, container):
        from app.core.service_container import ServiceContainer
        if not isinstance(container, ServiceContainer):
            raise TypeError(f"Expected ServiceContainer, got {type(container)}")
        
        self._db = container.router_config_db
        self._smart_router_service = container.smart_router_service

    async def get(self, config_id: str) -> RouterConfigResponse:
        record = await self._db.get_by_id(config_id)
        if record is None:
            raise RouterConfigNotFoundError(config_id)
        return RouterConfigResponse.model_validate(record)

    async def list_all(self) -> list[RouterConfigResponse]:
        records = await self._db.list_all()
        return [RouterConfigResponse.model_validate(r) for r in records]

    async def update(
        self, config_id: str, payload: RouterConfigUpdate
    ) -> RouterConfigResponse:
        # Only fields explicitly passed in by the caller are written to the database (exclude_none=True implements partial update).
        update_data = payload.model_dump(exclude_none=True)

        if not update_data:
            # If the caller passes an empty body, simply return the existing record.
            return await self.get(config_id)

        record = await self._db.update(config_id, update_data)
        if record is None:
            raise RouterConfigNotFoundError(config_id)
        
        if not self._smart_router_service:
            self._smart_router_service.invalidate(router_config_id=config_id)

        return RouterConfigResponse.model_validate(record)

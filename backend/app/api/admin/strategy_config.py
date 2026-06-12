#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-11
# @description: Strategy Config Router


from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from app.core.security.auth_permission import AuthPermission
from app.schemas.common import ApiResponse

from app.schemas.admin.strategy_config import (
    StrategyConfigCreate,
    StrategyConfigListOut,
    StrategyConfigOut,
    StrategyConfigUpdate,
)
from app.services.admin.strategy_config import StrategyConfigService

router = APIRouter()

# ──────────────────────────────────────────────
# Service dependency
# ──────────────────────────────────────────────

def get_service(request: Request) -> StrategyConfigService:
    return request.app.state.container.strategy_config_service

_list   = AuthPermission.Permission("strategy_config:list")
_add    = AuthPermission.Permission("strategy_config:add")
_edit   = AuthPermission.Permission("strategy_config:edit")
_delete = AuthPermission.Permission("strategy_config:delete")

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ApiResponse[StrategyConfigOut],   
    summary="Create a new strategy config",
)
async def create_strategy_config(
    payload: StrategyConfigCreate,
    svc: StrategyConfigService = Depends(get_service),
    caller_id: int            = Depends(_add),
) -> ApiResponse[StrategyConfigOut]:
    data = await svc.create(payload)
    return ApiResponse(data=data)


@router.get(
    "/{config_id}",
    response_model=ApiResponse[StrategyConfigOut],
    summary="Get a strategy config by ID",
)
async def get_strategy_config(
    config_id: str,
    svc: StrategyConfigService = Depends(get_service),
    caller_id: int            = Depends(_list),
) -> ApiResponse[StrategyConfigOut]:
    data = await svc.get(config_id)
    return ApiResponse(data=data)


@router.get(
    "/kb/{kb_id}/active",
    response_model=ApiResponse[StrategyConfigOut],
    summary="Get the active strategy config for a knowledge base",
)
async def get_active_config(
    kb_id: int,
    svc: StrategyConfigService = Depends(get_service),
    caller_id: int            = Depends(_list),
) -> ApiResponse[StrategyConfigOut]:
    data = await svc.get_active(kb_id)
    return ApiResponse(data=data)


@router.get(
    "/kb/{kb_id}",
    response_model=ApiResponse[StrategyConfigListOut],
    summary="List all strategy configs for a knowledge base (paginated)",
)
async def list_strategy_configs(
    kb_id: int,
    page: int = 1,
    page_size: int = 20,
    svc: StrategyConfigService = Depends(get_service),
    caller_id: int            = Depends(_list),
) -> ApiResponse[StrategyConfigListOut]:
    data = await svc.list(kb_id, page, page_size)
    return ApiResponse(data=data)

@router.get(
    "",
    response_model=ApiResponse,
    summary="List all strategy configs (paginated)",
    description="Return a paginated list of all strategy configs, optionally filtered by kb_id or is_active.",
)
async def list_all_strategy_configs(
    kb_id: Optional[int] = Query(None, description="Filter by knowledge base ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    svc:       StrategyConfigService   = Depends(get_service),
    caller_id: int            = Depends(_list),
) -> ApiResponse:
    data = await svc.list_all(
        kb_id=kb_id,
        is_active=is_active,
        page=page,
        page_size=page_size
    )
    return ApiResponse(data=data)

@router.patch(
    "/{config_id}",
    response_model=ApiResponse[StrategyConfigOut],
    summary="Partially update a strategy config",
)
async def update_strategy_config(
    config_id: str,
    payload: StrategyConfigUpdate,
    svc: StrategyConfigService = Depends(get_service),
    caller_id: int            = Depends(_edit),
) -> ApiResponse[StrategyConfigOut]:
    data = await svc.update(config_id, payload)
    return ApiResponse(data=data)


@router.delete(
    "/{config_id}",
    response_model=ApiResponse[int],
    summary="Delete a strategy config",
)
async def delete_strategy_config(
    config_id: str,
    svc: StrategyConfigService = Depends(get_service),
    caller_id: int            = Depends(_delete),
) -> ApiResponse[int]:
    kb_id = await svc.delete(config_id)
    return ApiResponse(data=kb_id, message="Deleted successfully")


@router.post(
    "/{config_id}/activate",
    response_model=ApiResponse[StrategyConfigOut],
    summary="Activate a strategy config (deactivates all others in the same KB)",
)
async def activate_strategy_config(
    config_id: str,
    svc: StrategyConfigService = Depends(get_service),
    caller_id: int            = Depends(_edit),
) -> ApiResponse[StrategyConfigOut]:
    data = await svc.activate(config_id)
    return ApiResponse(data=data)

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-08
# @description: Tool/Skill API Router

from fastapi import APIRouter, Depends, Request

from app.schemas.admin.router_config import RouterConfigUpdate
from app.services.admin.router_config import RouterConfigService
from app.schemas.common import ApiResponse
from app.core.security.auth_permission import AuthPermission

router = APIRouter()

# ──────────────────────────────────────────────
# Service dependency
# ──────────────────────────────────────────────

def get_service(request: Request) -> RouterConfigService:
    return request.app.state.container.router_config_service

_list_router_config   = AuthPermission.Permission("router_config:list")
_edit_router_config   = AuthPermission.Permission("router_config:edit")

@router.get(
    "",
    response_model=ApiResponse,
    summary="Get all routing policy configurations",
)
async def list_router_configs(
    _svc:       RouterConfigService   = Depends(get_service),
    caller_id: int            = Depends(_list_router_config),
):
    list = await _svc.list_all()
    result = ApiResponse(data=list)
    return result

@router.get(
    "/{config_id}",
    response_model=ApiResponse,
    summary="Query single route policy configuration",
)
async def get_router_config(
    config_id: str,
    _svc:       RouterConfigService   = Depends(get_service),
    caller_id: int            = Depends(_list_router_config)
):
    config = await _svc.get(config_id)
    result = ApiResponse(data=config)
    return result

@router.patch(
    "/{config_id}",
    response_model=ApiResponse,
    summary="Edit routing policy configuration (partial update)",
)
async def update_router_config(
    config_id:          str, 
    payload:            RouterConfigUpdate,
    _svc:               RouterConfigService     = Depends(get_service), 
    caller_id:          int                     = Depends(_edit_router_config)
):
  
    await _svc.update(config_id, payload)
    return ApiResponse()
   
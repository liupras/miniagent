#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-08
# @description: Tool/Skill API Router

from fastapi import APIRouter, Depends, Request

from app.core.security.auth_permission import AuthPermission
from app.schemas.admin.router_config import RouterConfigUpdate
from app.services.admin.router_config import RouterConfigService
from app.schemas.common import ApiResponse
from app.services.kb.service_smart_router import KBSmartRouterService

router = APIRouter()

# ──────────────────────────────────────────────
# Service dependency
# ──────────────────────────────────────────────

def get_service(request: Request) -> RouterConfigService:
    return request.app.state.container.router_config_service

def get_service_smart_router(
    request: Request
) -> KBSmartRouterService:
    """
    Return the long-lived KBSmartRouterService singleton from ServiceContainer.

    The service delegates to SmartRouterFactory, which caches one SmartRouter
    per router_config_id.  Must be a singleton — never recreate per request.

    Call container.smart_router_service.invalidate(router_config_id) after
    updating a RouterConfig in the DB.
    """
    return request.app.state.container.smart_router_service

_list   = AuthPermission.Permission("router_config:list")
_edit   = AuthPermission.Permission("router_config:edit")

@router.get(
    "/",
    response_model=ApiResponse,
    summary="Get all routing policy configurations",
)
async def list_router_configs(
    _svc:       RouterConfigService   = Depends(get_service),
    caller_id: int            = Depends(_list),
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
    caller_id: int            = Depends(_list)
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
    _svc_smart_router:  KBSmartRouterService    = Depends(get_service_smart_router),
    caller_id:          int                     = Depends(_edit)
):
  
    await _svc.update(config_id, payload)
    _svc_smart_router.invalidate(config_id)
    return ApiResponse()
   
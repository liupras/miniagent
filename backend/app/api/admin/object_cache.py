#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-29
# @description: Object Cache API Router 

#
# 集成说明（请按项目实际情况调整）：
# 1. `get_service` 假设 ServiceContainer 上已挂载 `cache_registry: CacheRegistry` 属性，
#    与项目里 SQLAgentService / WebSearchService 等服务同样通过 Depends(get_service_container) 获取。
# 2. 权限校验沿用项目 RBAC 惯例，示例中用 `require_permission("system:cache:xxx")` 占位，
#    请替换为项目里实际的权限依赖（对应超管通配符 "*:*:*"）。
# 3. 统一走 BaseDomainError -> 全局异常处理器 -> HTTP 200 + 业务错误码 的约定，
#    因此这里只抛领域异常，不手写 HTTPException。

from __future__ import annotations

from typing import Dict, Optional
from fastapi import APIRouter, Depends, Query, Request

from app.schemas.common import ApiResponse
from app.runtime.cache.registry import CacheRegistry
from app.core.security.auth_permission import AuthPermission

from app.schemas.admin.object_cache import (
    CacheInvalidateAllResponse,
    CacheInvalidateEverywhereRequest,
    CacheInvalidateEverywhereResponse,
    CacheInvalidateRequest,
    CacheInvalidateResponse,
    CacheStatsItem,
)

router = APIRouter()

def get_service(request: Request) -> CacheRegistry:
    return request.app.state.container.cache_registry

_list   = AuthPermission.Permission("object_cache:list")
_edit   = AuthPermission.Permission("object_cache:edit")

@router.get(
    "/list",
    response_model=ApiResponse[list[str]],
    summary="Get all registered cached names"
)
async def list_caches(
    svc:       CacheRegistry   = Depends(get_service),
    caller_id: int            = Depends(_list),   
) -> ApiResponse[list[str]]:
    data = svc.list_names()
    return ApiResponse(data=data)


@router.get(
    "/stats",
    response_model=ApiResponse[Dict[str, CacheStatsItem]],
    summary="Retrieve cache statistics; if name is empty, return all cached data.",   
)
async def get_cache_stats(
    name: Optional[str] = Query(None, description="Cache name; if empty, return statistics for all caches."),
    svc:       CacheRegistry   = Depends(get_service),
    caller_id: int            = Depends(_list), 
) -> ApiResponse[Dict[str, CacheStatsItem]]:

    stats = svc.stats(name)    
    return ApiResponse(data=stats)


@router.post(
    "/{name}/invalidate",
    response_model=ApiResponse[CacheInvalidateResponse],
    summary="Invalidate a specified record in the cache by key.",    
)
async def invalidate_cache_key(
    name: str,
    body: CacheInvalidateRequest,
    svc:       CacheRegistry   = Depends(get_service),
    caller_id: int            = Depends(_edit),
) -> ApiResponse[CacheInvalidateResponse]:
        
    invalidated = svc.invalidate(name, body.key)
    return ApiResponse(
        data=CacheInvalidateResponse(name=name, key=body.key, invalidated=invalidated)
    )

@router.post(
    "/{name}/invalidate-all",
    response_model=ApiResponse[CacheInvalidateAllResponse],
    summary="Invalidate all records in a specified cache.",    
)
async def invalidate_cache_all(
    name: str,
    svc:       CacheRegistry   = Depends(get_service),
    caller_id: int            = Depends(_edit),
) -> ApiResponse[CacheInvalidateAllResponse]:
  
    count = svc.invalidate_all(name)
    return ApiResponse(data=CacheInvalidateAllResponse(name=name, count=count))


@router.post(
    "/invalidate-everywhere",
    response_model=ApiResponse[CacheInvalidateEverywhereResponse],
    summary="Invalidate a specified record in all registered caches by key.",    
)
async def invalidate_cache_everywhere(
    body: CacheInvalidateEverywhereRequest,
    svc:       CacheRegistry   = Depends(get_service),
    caller_id: int            = Depends(_edit),
) -> ApiResponse[CacheInvalidateEverywhereResponse]:
    
    results = svc.invalidate_everywhere(body.key)
    return ApiResponse(
        data=CacheInvalidateEverywhereResponse(key=body.key, results=results)
    )

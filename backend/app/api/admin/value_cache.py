#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-04
# @description: Cache Store (LangChain BaseStore) Admin API Router

from __future__ import annotations

from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, Query, Request

from app.schemas.common import ApiResponse
from app.infra.cache.store_registry import CacheStoreRegistry
from app.core.security.auth_permission import AuthPermission

from app.schemas.admin.value_cache import (
    CacheStoreStatsItem,
    CacheStoreKeysResponse,
    CacheStoreDeleteKeysRequest,
    CacheStoreDeleteKeysResponse,
    CacheStoreClearResponse,
    CacheStoreClearAllResponse,
)

router = APIRouter()

def get_service(request: Request) -> CacheStoreRegistry:
    return request.app.state.container.value_cache_registry


_list = AuthPermission.Permission("value_cache:list")
_edit = AuthPermission.Permission("value_cache:edit")

from app.core.i18n.i18n import t
def _ensure_namespace(svc: CacheStoreRegistry, namespace: str) -> None:
    if not svc.has_namespace(namespace):
        raise KeyError(t("namespace_not_found", namespace=namespace))

@router.get(
    "/list",
    response_model=ApiResponse[List[str]],
    summary="Get all registered cache store namespaces",
)
async def list_namespaces(
    svc: CacheStoreRegistry = Depends(get_service),
    caller_id: int = Depends(_list),
) -> ApiResponse[List[str]]:
    data = svc.list_namespaces()
    return ApiResponse(data=data)


@router.get(
    "/stats",
    response_model=ApiResponse[Dict[str, CacheStoreStatsItem]],
    summary="Get stats for all namespaces; if `namespace` is given, return just that one",
)
async def get_stats(
    namespace: Optional[str] = Query(None, description="Namespace; if empty, returns statistics for all namespaces."),
    svc: CacheStoreRegistry = Depends(get_service),
    caller_id: int = Depends(_list),
) -> ApiResponse[Dict[str, CacheStoreStatsItem]]:
    if namespace:
        _ensure_namespace(svc, namespace)
        data = {namespace: svc.get_namespace_stats(namespace)}
    else:
        data = svc.get_all_stats()
    return ApiResponse(data=data)


@router.get(
    "/{namespace}/keys",
    response_model=ApiResponse[CacheStoreKeysResponse],
    summary="List keys under a namespace, optionally filtered by prefix",
)
async def get_keys(
    namespace: str,
    prefix: Optional[str] = Query(None, description="Filter by prefix"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of keys to return, to avoid overwhelming the page"),
    svc: CacheStoreRegistry = Depends(get_service),
    caller_id: int = Depends(_list),
) -> ApiResponse[CacheStoreKeysResponse]:
    _ensure_namespace(svc, namespace)
    keys = svc.get_keys(namespace, prefix=prefix, limit=limit)
    return ApiResponse(
        data=CacheStoreKeysResponse(
            namespace=namespace,
            keys=keys,
            prefix=prefix,
            limit=limit,
            truncated=len(keys) >= limit,
        )
    )


@router.post(
    "/{namespace}/delete-keys",
    response_model=ApiResponse[CacheStoreDeleteKeysResponse],
    summary="Delete specified keys under a namespace",
)
async def delete_keys(
    namespace: str,
    body: CacheStoreDeleteKeysRequest,
    svc: CacheStoreRegistry = Depends(get_service),
    caller_id: int = Depends(_edit),
) -> ApiResponse[CacheStoreDeleteKeysResponse]:
    _ensure_namespace(svc, namespace)
    count = svc.delete_keys(namespace, body.keys)
    return ApiResponse(
        data=CacheStoreDeleteKeysResponse(namespace=namespace, deleted_count=count)
    )


@router.post(
    "/{namespace}/clear",
    response_model=ApiResponse[CacheStoreClearResponse],
    summary="Clear all keys under a namespace",
)
async def clear_namespace(
    namespace: str,
    svc: CacheStoreRegistry = Depends(get_service),
    caller_id: int = Depends(_edit),
) -> ApiResponse[CacheStoreClearResponse]:
    _ensure_namespace(svc, namespace)
    count = svc.clear_namespace(namespace)
    return ApiResponse(
        data=CacheStoreClearResponse(namespace=namespace, cleared_count=count)
    )


@router.post(
    "/clear-all",
    response_model=ApiResponse[CacheStoreClearAllResponse],
    summary="Clear all registered namespaces",
)
async def clear_all(
    svc: CacheStoreRegistry = Depends(get_service),
    caller_id: int = Depends(_edit),
) -> ApiResponse[CacheStoreClearAllResponse]:
    results = svc.clear_all()
    return ApiResponse(data=CacheStoreClearAllResponse(results=results))

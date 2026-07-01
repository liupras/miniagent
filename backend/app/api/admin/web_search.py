#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-25
# @description: FastAPI router — Web Search endpoints

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.schemas.common import ApiResponse

router = APIRouter()

# ═══════════════════════════════════════════════════════════════════════════
# Dependency helper
# ═══════════════════════════════════════════════════════════════════════════

def _get_web_search_service(request: Request):
    """
    Resolve WebSearchService from app.state.container.
    """
    return request.app.state.container.web_search_service

from app.schemas.admin.web_search import CacheInfoResponse


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.delete(
    "/cache",
    response_model=ApiResponse,
    summary="Invalidate all pipeline caches",
    description="Evict every cached WebSearchPipeline.  Next call per tool rebuilds from DB.",
)
async def invalidate_all_cache(
    service=Depends(_get_web_search_service),
) -> ApiResponse:
    service.invalidate_all()
    return ApiResponse()


@router.delete(
    "/{tool_name}/cache",
    response_model=ApiResponse,
    summary="Invalidate pipeline cache for one tool",
    description=(
        "Evict the cached WebSearchPipeline for *tool_name*.  "
        "The next search call will reload the Tool config from the database and "
        "rebuild the pipeline."
    ),
)
async def invalidate_tool_cache(
    tool_name: str,
    service=Depends(_get_web_search_service),
) -> ApiResponse:
    service.invalidate(tool_name)
    return ApiResponse()


@router.get(
    "/cache/info",
    response_model=ApiResponse,
    summary="Get result-cache statistics",
    description=(
        "Return per-tool search-result cache statistics "
        "(hits, misses, size, TTL) for every currently cached pipeline. "
        "Returns an empty dict when no pipelines are cached yet."
    ),
)
async def cache_info(
    service=Depends(_get_web_search_service),
) -> ApiResponse:
    data = CacheInfoResponse(pipelines=service.cache_info())
    return ApiResponse(data=data)

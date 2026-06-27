#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-25
# @description: FastAPI router — Web Search endpoints

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

router = APIRouter()

# ═══════════════════════════════════════════════════════════════════════════
# Dependency helper
# ═══════════════════════════════════════════════════════════════════════════

def _get_web_search_service(request: Request):
    """
    Resolve WebSearchService from app.state.container.
    """
    return request.app.state.container.web_search_service


# ═══════════════════════════════════════════════════════════════════════════
# Request / Response schemas
# ═══════════════════════════════════════════════════════════════════════════

class CacheInfoResponse(BaseModel):
    """Per-tool result-cache statistics."""
    pipelines: dict = Field(description="Mapping of tool_name → cache stats dict (or null).")


class MessageResponse(BaseModel):
    message: str


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.delete(
    "/cache",
    response_model=MessageResponse,
    summary="Invalidate all pipeline caches",
    description="Evict every cached WebSearchPipeline.  Next call per tool rebuilds from DB.",
)
async def invalidate_all_cache(
    service=Depends(_get_web_search_service),
) -> MessageResponse:
    service.invalidate_all()
    return MessageResponse(message="All web-search pipeline caches have been cleared.")


@router.delete(
    "/{tool_name}/cache",
    response_model=MessageResponse,
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
) -> MessageResponse:
    service.invalidate(tool_name)
    return MessageResponse(
        message=f"Pipeline cache for tool {tool_name!r} has been cleared."
    )


@router.get(
    "/cache/info",
    response_model=CacheInfoResponse,
    summary="Get result-cache statistics",
    description=(
        "Return per-tool search-result cache statistics "
        "(hits, misses, size, TTL) for every currently cached pipeline. "
        "Returns an empty dict when no pipelines are cached yet."
    ),
)
async def cache_info(
    service=Depends(_get_web_search_service),
) -> CacheInfoResponse:
    return CacheInfoResponse(pipelines=service.cache_info())

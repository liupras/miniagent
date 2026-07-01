#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-25
# @description: FastAPI router — Web Search endpoints

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from loguru import logger

from app.schemas.common import ApiResponse
from app.core.i18n.i18n import t

from app.schemas.user.web_search import WebSearchRequest,WebSearchResultItem,WebSearchResponse,ForLLMResponse,MessageResponse

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
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/{tool_name}",
    response_model=ApiResponse,
    summary="Run web search",
    description=(
        "Execute a web search pipeline configured for *tool_name* and return "
        "structured results.  The pipeline is built from the Tool row in the "
        "database on first call and then cached for reuse."
    )
)
async def search(
    tool_name: str,
    body: WebSearchRequest,
    service=Depends(_get_web_search_service),
) -> ApiResponse:
    
    state = await service.search(
        tool_name=tool_name, 
        query=body.query,
        llm_provider_id=body.llm_provider_id
    )

    results = [
        WebSearchResultItem(
            title         = r.title,
            url           = r.url,
            snippet       = r.snippet,
            content       = r.content,
            position      = r.position,
            final_score   = r.final_score,
            rerank_score  = r.rerank_score,
            pipeline_path = r.pipeline_path,
        )
        for r in state.results
    ]

    data = WebSearchResponse(
        tool_name       = tool_name,
        original_query  = state.original_query,
        rewritten_query = state.rewritten_query or state.original_query,
        cache_hit       = state.cache_hit,
        result_count    = len(results),
        results         = results,
    )
    return ApiResponse(data=data)


@router.post(
    "/{tool_name}/for-llm",
    response_model=ApiResponse,
    summary="Run web search and return LLM context",
    description=(
        "Execute the web search pipeline for *tool_name* and return the results "
        "pre-formatted as a plain-text context block suitable for injection into "
        "an LLM prompt."
    ),
)
async def search_for_llm(
    tool_name: str,
    body: WebSearchRequest,
    service=Depends(_get_web_search_service),
) -> ApiResponse:
    
    state   = await service.search(tool_name, body.query)
    context = service._pipeline_cache[tool_name].__class__.format_for_llm(state)

    data = ForLLMResponse(
        tool_name       = tool_name,
        original_query  = state.original_query,
        rewritten_query = state.rewritten_query or state.original_query,
        cache_hit       = state.cache_hit,
        context         = context,
    )
    return ApiResponse(data=data)
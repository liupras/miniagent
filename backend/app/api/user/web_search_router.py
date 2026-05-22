#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-25
# @description: FastAPI router — Web Search endpoints

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

router = APIRouter()

# ═══════════════════════════════════════════════════════════════════════════
# Dependency helper
# ═══════════════════════════════════════════════════════════════════════════

def _get_web_search_service(request: Request):
    """
    Resolve WebSearchService from app.state.container.

    ServiceContainer must expose  ``web_search_service`` attribute, e.g.:
        self.web_search_service = WebSearchService(self)
    """
    container = request.app.state.container
    service = getattr(container, "web_search_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WebSearchService is not registered in ServiceContainer.",
        )
    return service


# ═══════════════════════════════════════════════════════════════════════════
# Request / Response schemas
# ═══════════════════════════════════════════════════════════════════════════

class WebSearchRequest(BaseModel):
    """Request body for all search endpoints."""
    query: str = Field(..., min_length=1, max_length=2000, description="User search query.")
    llm_provider_id:int = Field(default=1, description="LLM config Id.")

class WebSearchResultItem(BaseModel):
    """A single search result returned to the client."""
    title:        str
    url:          str
    snippet:      str
    content:      str
    position:     int
    final_score:  float
    rerank_score: float
    pipeline_path: List[str]


class WebSearchResponse(BaseModel):
    """Structured response for the /web-search/{tool_name} endpoint."""
    tool_name:       str
    original_query:  str
    rewritten_query: str
    cache_hit:       bool
    result_count:    int
    results:         List[WebSearchResultItem]


class ForLLMResponse(BaseModel):
    """Response for the /web-search/{tool_name}/for-llm endpoint."""
    tool_name:       str
    original_query:  str
    rewritten_query: str
    cache_hit:       bool
    context:         str = Field(description="Formatted context block ready for LLM injection.")


class MessageResponse(BaseModel):
    message: str


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/{tool_name}",
    response_model=WebSearchResponse,
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
) -> WebSearchResponse:
    try:
        state = await service.search(
            tool_name=tool_name, 
            query=body.query,
            llm_provider_id=body.llm_provider_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search pipeline error: {exc}",
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

    return WebSearchResponse(
        tool_name       = tool_name,
        original_query  = state.original_query,
        rewritten_query = state.rewritten_query or state.original_query,
        cache_hit       = state.cache_hit,
        result_count    = len(results),
        results         = results,
    )


@router.post(
    "/{tool_name}/for-llm",
    response_model=ForLLMResponse,
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
) -> ForLLMResponse:
    try:
        state   = await service.search(tool_name, body.query)
        context = service._pipeline_cache[tool_name].__class__.format_for_llm(state)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search pipeline error: {exc}",
        )

    return ForLLMResponse(
        tool_name       = tool_name,
        original_query  = state.original_query,
        rewritten_query = state.rewritten_query or state.original_query,
        cache_hit       = state.cache_hit,
        context         = context,
    )
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-28
# @description: Data Contract for web search

from typing import List

from pydantic import BaseModel, Field


class WebSearchRequest(BaseModel):
    """Request body for all search endpoints."""
    query: str = Field(..., min_length=1, max_length=2000, description="User search query.")   
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
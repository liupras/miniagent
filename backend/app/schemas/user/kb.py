#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-28
# @description: Data Contract for KB

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChunkResultSchema(BaseModel):
    chunk_id:       Any
    doc_id:         int
    kb_id:          int
    text:           str
    final_score:    float
    vector_score:   Optional[float] = None
    bm25_score:     Optional[float] = None
    rrf_score:      Optional[float] = None
    rerank_score:   Optional[float] = None
    retrieval_path: List[str]       = []
    metadata:       Dict[str, Any]  = {}


class QueryResponse(BaseModel):
    kb_id:      int
    query:      str
    confidence: str   = Field(..., description="Confidence level: 'high' | 'low' | 'empty'.")
    warning:    Optional[str] = Field(None, description="Low-confidence warning message.")
    chunks:     List[ChunkResultSchema]

class SmartRouterQueryRequest(BaseModel):
    """Request body for POST /smart-router/{router_config_id}/query."""

    query:           str            = Field(..., min_length=1, description="Natural-language query.")
    kb_ids:          List[int]      = Field(..., min_items=1,  description="Candidate KB ids.")
    metadata_filter: Optional[Dict[str, Any]] = Field(
        None, description="Optional metadata filter forwarded to every KB pipeline."
    )


class SmartRouterQueryResponse(BaseModel):
    """Response body for POST /smart-router/{router_config_id}/query."""

    router_config_id: str
    query:            str
    confidence:       str  = Field(..., description="Aggregated confidence: 'high' | 'low' | 'empty'.")
    warning:          Optional[str] = Field(None, description="Aggregated warning (None when high-confidence).")
    selected_kb_ids:  List[int]     = Field(..., description="KB ids that actually contributed chunks.")
    chunks:           List[ChunkResultSchema]
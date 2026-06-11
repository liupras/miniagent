#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-11
# @description: Strategy Config Pydantic Schemas

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# StrategyConfig schemas
# ---------------------------------------------------------------------------

class StrategyConfigBase(BaseModel):
    """Shared readable fields."""
    prompt_language: Optional[str] = None

    # Component switches
    enable_query_rewrite: bool = True
    enable_query_expansion: bool = False
    enable_query_hyde: bool = False
    enable_vector: bool = True
    enable_bm25: bool = True
    enable_reranker: bool = True
    enable_small_to_big: bool = True
    require_citation: bool = True

    # Search parameters
    query_expansion_num: int = 3
    max_transform_queries: int = 5
    vector_top_k: int = 30
    bm25_top_k: int = 30
    rrf_mode: str = "rrf"
    rrf_k: int = 60
    rrf_top_k: int = 20
    vector_weight: float = 0.6
    reranking_mode: str = "hybrid"
    rerank_top_k: int = 10
    final_top_k: int = 3

    # Threshold parameters
    vector_score_threshold: float = 0.5
    bm25_score_threshold: float = 0.1

    # Confidence
    confidence_high_score_threshold: float = 0.7
    confidence_min_high_conf_count: int = 1
    confidence_low_score_threshold: float = 0.5

    # Extra
    extra_config: Optional[dict[str, Any]] = None


class StrategyConfigCreate(StrategyConfigBase):
    """Fields required when creating a new config."""
    config_id: str = Field(..., max_length=100)
    kb_id: int
    version: int
    created_by: Optional[str] = None


class StrategyConfigUpdate(StrategyConfigBase):
    """All fields optional for partial update."""
    prompt_language: Optional[str] = None
    enable_query_rewrite: Optional[bool] = None
    enable_query_expansion: Optional[bool] = None
    enable_query_hyde: Optional[bool] = None
    enable_vector: Optional[bool] = None
    enable_bm25: Optional[bool] = None
    enable_reranker: Optional[bool] = None
    enable_small_to_big: Optional[bool] = None
    require_citation: Optional[bool] = None
    query_expansion_num: Optional[int] = None
    max_transform_queries: Optional[int] = None
    vector_top_k: Optional[int] = None
    bm25_top_k: Optional[int] = None
    rrf_mode: Optional[str] = None
    rrf_k: Optional[int] = None
    rrf_top_k: Optional[int] = None
    vector_weight: Optional[float] = None
    reranking_mode: Optional[str] = None
    rerank_top_k: Optional[int] = None
    final_top_k: Optional[int] = None
    vector_score_threshold: Optional[float] = None
    bm25_score_threshold: Optional[float] = None
    confidence_high_score_threshold: Optional[float] = None
    confidence_min_high_conf_count: Optional[int] = None
    confidence_low_score_threshold: Optional[float] = None
    extra_config: Optional[dict[str, Any]] = None


class StrategyConfigOut(StrategyConfigBase):
    """Response shape."""
    config_id: str
    kb_id: int
    version: int
    is_active: bool
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None

    model_config = {"from_attributes": True}


class StrategyConfigListOut(BaseModel):
    total: int
    items: list[StrategyConfigOut]

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-04
# @description: Pydantic schemas for the Cache Store (LangChain BaseStore) admin API

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CacheStoreStatsItem(BaseModel):
    """Statistics for a single namespace are shown in the return value of CacheStoreRegistry.get_namespace_stats."""
    namespace: str
    backend_type: str
    size: Optional[int] = None
    backend_stats: Optional[Dict[str, Any]] = None
    sample_keys: Optional[List[str]] = None


class CacheStoreKeysResponse(BaseModel):
    namespace: str
    keys: List[str]
    prefix: Optional[str] = None
    limit: int
    truncated: bool = Field(
        description="True indicates there may be more keys not returned (limit reached), requiring a smaller prefix range"
    )


class CacheStoreDeleteKeysRequest(BaseModel):
    keys: List[str]


class CacheStoreDeleteKeysResponse(BaseModel):
    namespace: str
    deleted_count: int


class CacheStoreClearResponse(BaseModel):
    namespace: str
    cleared_count: int


class CacheStoreClearAllResponse(BaseModel):
    results: Dict[str, int]

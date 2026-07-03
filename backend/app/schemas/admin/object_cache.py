#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-03
# @description: LLM Pydantic Schemas
# @description: Request/response model for cache management interface.

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CacheStatsItem(BaseModel):
    """Statistics for a single AsyncLazyCache instance are the return values ​​of AsyncLazyCache.stats()."""

    name: str = Field(..., description="Cache Name")
    size: int = Field(..., description="Current Number of Cache Entries")
    keys: List[Any] = Field(default_factory=list, description="List of All Cache Keys")
    description: str = Field("", description="Cache Usage Description")


class CacheInvalidateRequest(BaseModel):
    """Request body for invalidating a single cache entry by key. The key is in its original JSON form (str / list / dict),
    and the backend will decode it to the actual key used (e.g., tuple) using the key_codec provided during cache registration."""

    key: Any = Field(..., description="Original key, must match the form expected by the cache's key_codec")


class CacheInvalidateResponse(BaseModel):
    name: str
    key: Any
    invalidated: bool = Field(..., description="Whether the cache entry was matched and successfully invalidated")


class CacheInvalidateAllResponse(BaseModel):
    name: str
    count: int = Field(..., description="Number of entries cleared this time")


class CacheInvalidateEverywhereRequest(BaseModel):
    key: Any = Field(..., description="Original key, will attempt to decode and invalidate all registered caches")


class CacheInvalidateEverywhereResponse(BaseModel):
    key: Any
    results: Dict[str, bool] = Field(
        ..., description="Results for each cache name; caches with mismatched key forms will be safely skipped, resulting in false"
    )


class CacheStatsQuery(BaseModel):
    name: Optional[str] = Field(None, description="Cache Name, returns statistics for all caches if empty")

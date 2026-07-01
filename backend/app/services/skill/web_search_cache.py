#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-01
# @description: WebSearch result cache  (backed by MemoryCacheStore from cache_backend)

import hashlib
import json
from typing import List, Optional

from app.infra.cache_backend import create_cache_backend
from app.services.skill.web_search_models import WebSearchResult


class SearchResultCache:
    """
    Thin facade over MemoryCacheStore that handles serialisation and key
    encoding for WebSearchResult lists.

    TTL is delegated entirely to MemoryCacheStore.mset_with_ttl / mget_ttl
    — no timestamp bookkeeping lives in this class.

    Key encoding  : sha256(query.strip().lower()) — stable & collision-resistant.
    Serialisation : List[WebSearchResult] ↔ JSON bytes via to_dict() / from_dict().
    """

    def __init__(self, max_size: int = 256, ttl: int = 3600):
        self._ttl   = ttl
        self._store = create_cache_backend(max_size=max_size)

    def _make_key(self, query: str) -> str:
        return hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()

    def get(self, query: str) -> Optional[List[WebSearchResult]]:
        key = self._make_key(query)
        raw = self._store.mget_ttl([key])[0]
        if raw is None:
            return None
        try:
            return [WebSearchResult.from_dict(d) for d in json.loads(raw)]
        except (json.JSONDecodeError, KeyError):
            self._store.mdelete([key])
            return None

    def set(self, query: str, results: List[WebSearchResult]) -> None:
        key     = self._make_key(query)
        payload = json.dumps(
            [r.to_dict() for r in results], ensure_ascii=False
        ).encode()
        self._store.mset_with_ttl([(key, payload)], ttl_seconds=self._ttl)
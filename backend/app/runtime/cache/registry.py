#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-01
# @description: Central registry for all AsyncLazyCache instances.

from __future__ import annotations
from typing import Callable, Dict, Any, List, Optional
from .lazy_cache import AsyncLazyCache

from app.core.i18n.i18n import t

class CacheRegistry:
    """
    The central registry for all AsyncLazyCache instances.

    key_codec: Converts the raw JSON key (str / list / dict) from the backend interface into a hashable key (such as a tuple) actually used by the cache.
    """

    def __init__(self) -> None:
        self._caches: Dict[str, AsyncLazyCache] = {}
        self._key_codecs: Dict[str, Callable[[Any], Any]] = {}

    def register(
        self,
        name: str,
        cache: AsyncLazyCache,
        key_codec: Optional[Callable[[Any], Any]] = None,
    ) -> None:
        """
        `key_codec` defaults to an identity mapping (applies to str/int type keys).

        For tuple type keys, pass in a function that converts a list to a tuple, for example:
        `key_codec=lambda raw: (raw[0], raw[1])`
        """
        self._caches[name] = cache
        self._key_codecs[name] = key_codec or (lambda raw: raw)

    def _exists(self, name: str) -> AsyncLazyCache:
        if name not in self._caches:
            raise KeyError(t("cache.not_found", name=name, count=len(self._caches)))
        return self._caches[name]

    def decode_key(self, name: str, raw_key: Any) -> Any:
        self._exists(name)
        try:
            return self._key_codecs[name](raw_key)
        except Exception as e:
            raise ValueError(t("cache.key_decode_error", name=name, raw_key=raw_key, e=e))

    def invalidate(self, name: str, raw_key: Any) -> bool:
        cache = self._exists(name)
        key = self.decode_key(name, raw_key)
        return cache.invalidate(key)

    def invalidate_all(self, name: str) -> int:
        return self._exists(name).invalidate_all()

    def invalidate_everywhere(self, raw_key: Any) -> Dict[str, bool]:
        """
        Across all registered caches, attempt to invalidate using the same original key.

        Caches with mismatched key formats will be safely skipped (without error messages or interrupting the overall process).
        """
        result: Dict[str, bool] = {}
        for name, cache in self._caches.items():
            try:
                key = self.decode_key(name, raw_key)
                result[name] = cache.invalidate(key)
            except (ValueError, TypeError, IndexError):
                result[name] = False  # The key shape doesn't match, skip.
        return result

    def invalidate_where(self, name: str, predicate: Callable[[Any], bool]) -> int:
        return self._exists(name).invalidate_where(predicate)

    def list_names(self) -> List[str]:
        return list(self._caches.keys())

    def stats(self, name: Optional[str] = None) -> Dict[str, dict]:
        if name is not None:
            return {name: self._exists(name).stats()}
        return {n: c.stats() for n, c in self._caches.items()}
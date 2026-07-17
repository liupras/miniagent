#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-01
# @description: Object Cache Invalidator

from __future__ import annotations
from typing import Optional

from .models import CacheType
from .registry import CacheRegistry

class CacheInvalidationService:
    """
    Business-level cache invalidation service.    
    """

    def __init__(self, registry: CacheRegistry):
        self.registry = registry

    def on_agent_changed(self, agent_id: Optional[int]) -> None:
        if agent_id:
            self.registry.invalidate(CacheType.AGENT_RUNNER, agent_id)
        else:
           self.registry.invalidate_all(CacheType.AGENT_RUNNER) 

    def on_embedding_changed(self):
        self.registry.invalidate_all(CacheType.KB_RETRIEVAL_PIPELINE)
        self.registry.invalidate_all(CacheType.KB_EMBEDDING)

    def on_domain_changed(self):
        self.registry.invalidate_all(CacheType.KB_RETRIEVAL_PIPELINE)
        self.registry.invalidate_all(CacheType.VECTOR_STORE_MANAGER)
        self.registry.invalidate_all(CacheType.KB_INFO)
        self.registry.invalidate_all(CacheType.KB_EMBEDDING)

    def on_kb_changed(self, kb_id: int) -> None:

        self.registry.invalidate(CacheType.KB_INFO, kb_id)
        self.registry.invalidate(CacheType.KB_RETRIEVAL_PIPELINE,kb_id)
        self.registry.invalidate(CacheType.KB_EMBEDDING,kb_id)
        self.registry.invalidate(CacheType.VECTOR_STORE_MANAGER,kb_id)

    def on_llm_changed(self) -> None:

        self.registry.invalidate_all(CacheType.WEB_SEARCH_PIPELINE)
        self.registry.invalidate_all(CacheType.SQL_AGENT)
        self.registry.invalidate_all(CacheType.AGENT_RUNNER)
        self.registry.invalidate_all(CacheType.KB_RETRIEVAL_PIPELINE)

    def on_router_changed(self, router_config_id: int) -> None:

        self.registry.invalidate(CacheType.SMART_ROUTER,router_config_id)

    def on_strategy_changed(self):
        self.registry.invalidate_all(CacheType.KB_RETRIEVAL_PIPELINE)

    def on_tool_changed(self) -> None:
        """Tool configuration changed."""

        self.registry.invalidate_all(CacheType.WEB_SEARCH_PIPELINE)
        self.registry.invalidate_all(CacheType.SQL_AGENT)
        self.registry.invalidate_all(CacheType.AGENT_RUNNER)

    # ==========================================================
    # Global
    # ==========================================================

    def invalidate_all(self) -> None:
        for name in self.registry.list_names():
            self.registry.invalidate_all(name)
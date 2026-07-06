#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-05
# @description: Object cache models

from dataclasses import dataclass
from enum import StrEnum

class CacheType(StrEnum):
    WEB_SEARCH_PIPELINE = "web_search_pipeline"
    SQL_AGENT = "sql_agent"
    AGENT_RUNNER = "agent_runner"
    KB_RETRIEVAL_PIPELINE = "kb_retrieval_pipeline"
    KB_INFO = "kb_info"
    SMART_ROUTER = "smart_router"
    KB_EMBEDDING = "kb_embedding"
    VECTOR_STORE_MANAGER = "vector_store_manager"

@dataclass(frozen=True)
class CacheMeta:
    cache_type: CacheType
    key_name: str
    value_name: str
    location: str
    description: str


CACHE_META = {
    CacheType.WEB_SEARCH_PIPELINE: CacheMeta(
        CacheType.WEB_SEARCH_PIPELINE,
        "tool_name",
        "WebSearchPipeline",
        "WebSearchService",
        "Web search pipeline cache",
    ),
    CacheType.SQL_AGENT: CacheMeta(
        CacheType.SQL_AGENT,
        "tool_name",
        "SQLAgent",
        "SQLAgentService",
        "SQL agent cache",
    ),
    CacheType.AGENT_RUNNER: CacheMeta(
        CacheType.AGENT_RUNNER,
        "agent_id",
        "AgentRunner",
        "AgentFactory",
        "Agent runner cache",
    ),
    CacheType.KB_RETRIEVAL_PIPELINE: CacheMeta(
        CacheType.KB_RETRIEVAL_PIPELINE,
        "kb_id",
        "RetrievalPipeline",
        "KBRetrievalService",
        "Knowledge base retrieval pipeline cache",
    ),
    CacheType.KB_INFO: CacheMeta(
        CacheType.KB_INFO, 
        "kb_id",
        "KBInfo",
        "KBRetrievalService",
        "Knowledge base information cache",
    ),
    CacheType.SMART_ROUTER: CacheMeta(
        CacheType.SMART_ROUTER,
        "router_config_id",
        "SmartRouter",
        "SmartRouterFactory",
        "Smart router cache",
    ),
    CacheType.KB_EMBEDDING: CacheMeta(
        CacheType.KB_EMBEDDING,
        "kb_id",
        "Embedding",
        "SmartRouter",
        "Knowledge base embedding cache",
    ),
    CacheType.VECTOR_STORE_MANAGER: CacheMeta(
        CacheType.VECTOR_STORE_MANAGER,
        "kb_id",
        "VectorStoreManager",
        "VectorStoreRegistry",
        "Vector store manager cache",
    ),
}
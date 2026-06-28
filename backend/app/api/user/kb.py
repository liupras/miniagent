#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-27
# @description: FastAPI router — knowledge-base document CRUD with SSE progress.

from fastapi import (
    Request,
    APIRouter,
    Depends,
)

from loguru import logger

from app.services.kb.service_retrieval import QueryResult, KBRetrievalService
from app.services.kb.service_smart_router import KBSmartRouterService, SmartRouterQueryResult
from app.services.kb.retrieval_model import QueryRequest

from app.schemas.common import ApiResponse
from app.core.i18n.i18n import t
from app.schemas.user.kb import ChunkResultSchema,QueryResponse,SmartRouterQueryRequest,SmartRouterQueryResponse

# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────
router = APIRouter()

# ─────────────────────────────────────────────────────────────────
# Dependencies
# ─────────────────────────────────────────────────────────────────

from app.core.service_container import ServiceContainer

def get_container(request: Request) -> ServiceContainer:
    return request.app.state.container

def get_service_retrieval(
    container: ServiceContainer = Depends(get_container),
) -> KBRetrievalService:
    """
    Return the long-lived KBRetrievalService singleton from ServiceContainer.

    KBRetrievalService holds an in-memory pipeline cache keyed by
    (kb_id, config_id).  It must be a singleton — recreating it per request
    would reset the cache on every call.

    Call container.retrieval_service.invalidate(kb_id) after activating a
    new StrategyConfig version or changing the system language.
    """
    return container.retrieval_service

def get_service_smart_router(
    container: ServiceContainer = Depends(get_container),
) -> KBSmartRouterService:
    """
    Return the long-lived KBSmartRouterService singleton from ServiceContainer.

    The service delegates to SmartRouterFactory, which caches one SmartRouter
    per router_config_id.  Must be a singleton — never recreate per request.

    Call container.smart_router_service.invalidate(router_config_id) after
    updating a RouterConfig in the DB.
    """
    return container.smart_router_service

# ─────────────────────────────────────────────────────────────────────────────
# Query knowledge base — retrieval pipeline
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/{kb_id}/query",
    response_model=ApiResponse,
    summary="Query a knowledge base using the retrieval pipeline"
)
async def query_knowledge_base(
    kb_id:     int,
    body:      QueryRequest,
    container: ServiceContainer   = Depends(get_container),
    service:   KBRetrievalService = Depends(get_service_retrieval),
):
    """
    Execute the full retrieval pipeline for the given query against knowledge
    base `kb_id`.  Business logic is delegated to
    :meth:`KBRetrievalService.query`; this handler only validates inputs and
    maps service exceptions to HTTP status codes.

    The pipeline is built on first use and cached inside
    ``KBRetrievalService`` — subsequent calls to the same KB with the same
    active StrategyConfig reuse the cached pipeline with no rebuilding cost.
    """
    if not container.kb_db.kb_exists(kb_id):
        return ApiResponse(code=404,message=t("kb.not_found_with_id",kb_id=kb_id))

    try:
        result: QueryResult = await service.query(
            kb_id           = kb_id,
            query           = body.query,
            metadata_filter = body.metadata_filter,
        )
    except Exception as exc:
        logger.error(f"[query_knowledge_base]->{exc}")
        return ApiResponse(code=500,message=t("common.error_500"))

    data = QueryResponse(
        kb_id      = result.kb_id,
        query      = result.query,
        confidence = result.confidence,
        warning    = result.warning,
        chunks     = [ChunkResultSchema(**vars(c)) for c in result.chunks],
    )
    return ApiResponse(data=data)

# ─────────────────────────────────────────────────────────────────────────────
# Smart-router query — route across multiple knowledge bases
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/smart-router/{router_config_id}/query",
    response_model=ApiResponse,
    summary="Query multiple knowledge bases via smart router"
)
async def query_smart_router(
    router_config_id: str,
    body:             SmartRouterQueryRequest,
    service:          KBSmartRouterService = Depends(get_service_smart_router),
):
    """
    Route *query* to the most relevant subset of the supplied knowledge bases
    and return globally ranked chunks with an aggregated confidence level.

    **Routing strategies** (configured per ``router_config_id``):

    - ``keyword``  — select KBs whose keyword list matches the query.
    - ``embedding`` — rank KBs by cosine similarity of their description
      embedding to the query embedding; apply threshold / top-k fallback.

    When no KB matches the selection criteria and ``fallback_to_all=true`` in
    the RouterConfig, all supplied ``kb_ids`` are queried in parallel.

    The pipeline for each KB is built once and cached inside
    ``KBRetrievalService``; the SmartRouter itself is cached per
    ``router_config_id`` inside ``SmartRouterFactory``.
    """
    try:
        result: SmartRouterQueryResult = await service.query(
            router_config_id = router_config_id,
            query            = body.query,
            kb_ids           = body.kb_ids,
            metadata_filter  = body.metadata_filter,
        )
    except Exception as exc:
        logger.error(f"[query_smart_router]->{exc}")
        return ApiResponse(code=500,message=t("common.error_500"))

    data = SmartRouterQueryResponse(
        router_config_id = result.router_config_id,
        query            = result.query,
        confidence       = result.confidence,
        warning          = result.warning,
        selected_kb_ids  = result.selected_kb_ids,
        chunks           = [ChunkResultSchema(**vars(c)) for c in result.chunks],
    )
    return ApiResponse(data=data)
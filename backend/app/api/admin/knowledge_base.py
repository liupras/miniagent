#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-13
# @description: FastAPI router for KnowledgeBase management

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, Query, Request

from app.core.security.auth_permission import AuthPermission
from app.schemas.common import ApiResponse
from app.schemas.admin.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseListOut,
    KnowledgeBaseUpdate
)
from app.services.admin.knowledge_base import KnowledgeBaseService

_list   = AuthPermission.Permission("knowledge_base:list")
_add    = AuthPermission.Permission("knowledge_base:add")
_edit   = AuthPermission.Permission("knowledge_base:edit")
_delete = AuthPermission.Permission("knowledge_base:delete")

router = APIRouter()

def get_service(request: Request) -> KnowledgeBaseService:
    return request.app.state.container.kb_service

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=ApiResponse,
    summary="List knowledge bases",
    description="Return a paginated list of all knowledge bases, optionally filtered.",
)
async def list_kbs(
    name: Optional[str] = Query(None, description="Filter by knowledge base name"),
    domain_id: Optional[int] = Query(None, description="Filter by domain ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    svc:       KnowledgeBaseService   = Depends(get_service),
    caller_id: int            = Depends(_list),
) -> ApiResponse:
    total, items = await svc.list_kbs(
        name_filter=name,
        domain_id=domain_id,
        is_active=is_active,
        page=page,
        page_size=page_size
    )
    data = KnowledgeBaseListOut(total=total, page=page, page_size=page_size, items=items)
    return ApiResponse(data=data)


@router.get(
    "/options",
    response_model=ApiResponse,
    summary="Get knowledge base options",
    description="Return a list of knowledge bases for dropdown selection.",
)
async def get_kb_options(
    svc:       KnowledgeBaseService   = Depends(get_service),
) -> ApiResponse:
    data = await svc.get_kb_options()
    return ApiResponse(data=data)


@router.get(
    "/{kb_id}",
    response_model=ApiResponse,
    summary="Get a knowledge base by ID",
)
async def get_kb(
    kb_id: int,
    svc:       KnowledgeBaseService   = Depends(get_service),
    caller_id: int            = Depends(_list),
) -> ApiResponse:
    kb = await svc.get_kb(kb_id)
    return ApiResponse(data=kb)


@router.post(
    "",
    response_model=ApiResponse,
    summary="Create a new knowledge base",
)
async def create_kb(
    payload: KnowledgeBaseCreate,
    svc:       KnowledgeBaseService   = Depends(get_service),
    caller_id: int            = Depends(_add),
) -> ApiResponse:
    data = await svc.create_kb(payload)
    return ApiResponse(data=data)


@router.patch(
    "/{kb_id}",
    response_model=ApiResponse,
    summary="Partially update a knowledge base",
)
async def update_kb(
    kb_id: int,
    payload: KnowledgeBaseUpdate,
    svc:       KnowledgeBaseService   = Depends(get_service),
    caller_id: int            = Depends(_edit),
) -> ApiResponse:
    kb = await svc.update_kb(kb_id, payload)
    return ApiResponse(data= kb)


@router.delete(
    "/{kb_id}",
    response_model=ApiResponse,
    summary="Delete a knowledge base",
)
async def delete_kb(
    kb_id: int,
    svc:       KnowledgeBaseService   = Depends(get_service),
    caller_id: int            = Depends(_delete),
) -> ApiResponse:
    success = await svc.delete_kb(kb_id)   
    return ApiResponse(data=success)

@router.patch(
    "/{kb_id}/toggle",
    response_model=ApiResponse,
    summary="Toggle knowledge base active status",
)
async def toggle_kb_active(
    kb_id: int,
    svc:       KnowledgeBaseService   = Depends(get_service),
    caller_id: int            = Depends(_edit),
) -> ApiResponse:
    await svc.toggle_kb_active(kb_id)
    return ApiResponse()

@router.get(
    "/{kb_id}/stats",
    response_model=ApiResponse,
    summary="Get knowledge base statistics",
)
async def get_kb_stats(
    kb_id: int,
    svc:       KnowledgeBaseService   = Depends(get_service),
    caller_id: int            = Depends(_list),
) -> ApiResponse:
    stats = await svc.get_kb_stats(kb_id)
    return ApiResponse(data=stats)
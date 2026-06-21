#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: Embedding Router

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.security.auth_permission import AuthPermission
from app.schemas.admin.embedding import (
    EmbeddingCreate,
    EmbeddingListOut,
    EmbeddingUpdate,
)
from app.schemas.common import ApiResponse
from app.services.admin.embedding import EmbeddingService

_list   = AuthPermission.Permission("embedding:list")
_add    = AuthPermission.Permission("embedding:add")
_edit   = AuthPermission.Permission("embedding:edit")
_delete = AuthPermission.Permission("embedding:delete")

router = APIRouter()

def get_service(request: Request) -> EmbeddingService:
    return request.app.state.container.embedding_service

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=ApiResponse,
    summary="List embeddings",
    description="Return a paginated list of all embeddings, optionally filtered.",
)
async def list_embeddings(
    name: Optional[str] = Query(None, description="Filter by embedding name"),
    provider_name: Optional[str] = Query(None, description="Filter by provider name"),
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    svc:       EmbeddingService   = Depends(get_service),
    caller_id: int            = Depends(_list),
) -> ApiResponse:
    items, total = await svc.list_embeddings(
        name=name,
        provider_name=provider_name,
        page=page,
        page_size=page_size
    )
    data = EmbeddingListOut(total=total, page=page, page_size=page_size, items=items)
    return ApiResponse(data=data)


@router.get(
    "/options",
    response_model=ApiResponse,
    summary="Get embedding options for dropdown selection",
    description="Return a list of embeddings for dropdown selection.",
)
async def get_embedding_options(
    svc:       EmbeddingService   = Depends(get_service),
) -> ApiResponse:
    data = await svc.get_embedding_options()
    return ApiResponse(data=data)

@router.get(
    "/{embedding_id}",
    response_model=ApiResponse,
    summary="Get an embedding by ID",
)
async def get_embedding(
    embedding_id: int,
    svc:       EmbeddingService   = Depends(get_service),
    caller_id: int            = Depends(_list),
) -> ApiResponse:
    embedding = await svc.get_by_id(embedding_id)
    if not embedding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Embedding not found")
    return ApiResponse(data= embedding)


@router.post(
    "",
    response_model=ApiResponse,
    summary="Create a new embedding",
)
async def create_embedding(
    payload: EmbeddingCreate,
    svc:       EmbeddingService   = Depends(get_service),
    caller_id: int            = Depends(_add),
) -> ApiResponse:
    data = await svc.create(payload)
    return ApiResponse(data=data)


@router.patch(
    "/{embedding_id}",
    response_model=ApiResponse,
    summary="Partially update an embedding",
)
async def update_embedding(
    embedding_id: int,
    payload: EmbeddingUpdate,
    svc:       EmbeddingService   = Depends(get_service),
    caller_id: int            = Depends(_edit),
) -> ApiResponse:
    embedding = await svc.update(embedding_id, payload)
    if not embedding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Embedding not found")
    return ApiResponse(data= embedding)

@router.delete(
    "/{embedding_id}",
    response_model=ApiResponse,
    summary="Delete an embedding",
)
async def delete_embedding(
    embedding_id: int,
    svc:       EmbeddingService   = Depends(get_service),
    caller_id: int            = Depends(_delete),
) -> ApiResponse:
    row_count = await svc.delete(embedding_id)
    return ApiResponse(data=row_count)
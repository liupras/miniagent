#!/usr/bin/python
# -*- coding:utf-8 -*-

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.security.auth_permission import AuthPermission
from app.schemas.admin.prompt import (
    PromptBulkUpsert,
    PromptCreate,
    PromptUpdate,
)
from app.schemas.common import ApiResponse
from app.services.admin.prompt import PromptService

router = APIRouter()

_list = AuthPermission.Permission("prompt:list")
_add = AuthPermission.Permission("prompt:add")
_edit = AuthPermission.Permission("prompt:edit")
_delete = AuthPermission.Permission("prompt:delete")


def get_service(request: Request) -> PromptService:
    return request.app.state.container.prompt_service


@router.get("", response_model=ApiResponse, summary="Paginated prompt list")
async def list_prompts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    lang: Optional[str] = Query(None),
    service: PromptService = Depends(get_service),
    caller_id: int = Depends(_list),
):
    return ApiResponse(
        data=await service.list_prompts(
            page=page,
            page_size=page_size,
            keyword=keyword,
            lang=lang,
        )
    )


@router.get("/languages", response_model=ApiResponse, summary="Prompt languages")
async def list_languages(
    service: PromptService = Depends(get_service),
    caller_id: int = Depends(_list),
):
    return ApiResponse(data=await service.list_languages())


@router.get("/detail", response_model=ApiResponse, summary="Get prompt")
async def get_prompt(
    key: str = Query(..., min_length=1, max_length=200),
    lang: str = Query(..., min_length=2, max_length=10),
    service: PromptService = Depends(get_service),
    caller_id: int = Depends(_list),
):
    return ApiResponse(data=await service.get_prompt(key, lang))


@router.post(
    "",
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create prompt",
)
async def create_prompt(
    payload: PromptCreate,
    service: PromptService = Depends(get_service),
    caller_id: int = Depends(_add),
):
    return ApiResponse(data=await service.create(payload))


@router.put("/detail", response_model=ApiResponse, summary="Update prompt")
async def update_prompt(
    payload: PromptUpdate,
    key: str = Query(..., min_length=1, max_length=200),
    lang: str = Query(..., min_length=2, max_length=10),
    service: PromptService = Depends(get_service),
    caller_id: int = Depends(_edit),
):
    return ApiResponse(data=await service.update(key, lang, payload))


@router.post("/bulk-upsert", response_model=ApiResponse, summary="Bulk upsert prompts")
async def bulk_upsert_prompts(
    payload: PromptBulkUpsert,
    service: PromptService = Depends(get_service),
    caller_id: int = Depends(_edit),
):
    return ApiResponse(data=await service.bulk_upsert(payload))


@router.delete("/detail", response_model=ApiResponse, summary="Delete prompt")
async def delete_prompt(
    key: str = Query(..., min_length=1, max_length=200),
    lang: str = Query(..., min_length=2, max_length=10),
    service: PromptService = Depends(get_service),
    caller_id: int = Depends(_delete),
):
    await service.delete(key, lang)
    return ApiResponse()

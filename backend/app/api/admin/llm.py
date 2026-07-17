#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-29
# @description: LLM API Router – HTTP layer only, all logic lives in LLMService

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request, status

from app.schemas.admin.llm import (
    LLMCreate,
    LLMUpdate,
    LLMUpsert,
    LLMOut,
    LLMOptionItem,
    LLMListParams,
)
from app.schemas.common import PageResult, ApiResponse
from app.services.admin.llm import LLMService
from app.core.service_container import ServiceContainer

router = APIRouter()

# ──────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────

def get_container(request: Request) -> ServiceContainer:
    return request.app.state.container

def get_service(
    container: ServiceContainer = Depends(get_container),
) -> LLMService:
    return container.llm_service

# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@router.get(
    "/options",
    response_model=ApiResponse,
    summary="LLM dropdown options (id + name + provider + model)",
)
async def get_llm_options(
    provider_name: Optional[str] = Query(None, description="Filter by provider"),
    svc: LLMService = Depends(get_service),
):

    options: List[LLMOptionItem] = await svc.get_options(provider_name)
    return ApiResponse(data=options)


@router.get(
    "/providers",
    response_model=ApiResponse,
    summary="List all distinct provider names",
)
async def list_providers(svc: LLMService = Depends(get_service)):
    providers = await svc.list_providers()
    return ApiResponse(data=providers)


@router.get(
    "/models",
    response_model=ApiResponse,
    summary="List all distinct model names, optionally filtered by provider",
)
async def list_models(
    provider_name: Optional[str] = Query(None),
    svc: LLMService = Depends(get_service),
):
    models = await svc.list_models(provider_name)
    return ApiResponse(data=models)


@router.get("", response_model=ApiResponse, summary="Paginated LLM list")
async def list_llms(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    provider_name: Optional[str] = Query(None, description="Exact provider filter"),
    model_name: Optional[str] = Query(None, description="Fuzzy model name filter"),
    svc: LLMService = Depends(get_service),
):
    params = LLMListParams(
        page=page,
        page_size=page_size,
        provider_name=provider_name,
        model_name=model_name,
    )
    result: PageResult = await svc.list_llms(params)
    return ApiResponse(data=result)


@router.get("/{llm_id}", response_model=ApiResponse, summary="Get LLM by id")
async def get_llm(
    llm_id: int,
    svc: LLMService = Depends(get_service),
):
    row = await svc.get_llm(llm_id)
    return ApiResponse(data=LLMOut.model_validate(row))


@router.post(
    "",
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create LLM",
)
async def create_llm(
    payload: LLMCreate,
    svc: LLMService = Depends(get_service),
):
    llm_out = await svc.create_llm(payload)
    return ApiResponse(data=llm_out)


@router.put(
    "/upsert",
    response_model=ApiResponse,
    summary="Create or update LLM by (provider_name, model_name)",
)
async def upsert_llm(
    payload: LLMUpsert,
    svc: LLMService = Depends(get_service),
):
    llm_out = await svc.upsert_llm(payload)
    return ApiResponse(data=llm_out)


@router.put("/{llm_id}", response_model=ApiResponse, summary="Update LLM")
async def update_llm(
    llm_id: int,
    payload: LLMUpdate,
    svc: LLMService = Depends(get_service),   
):
    llm_out = await svc.update_llm(llm_id, payload)
    return ApiResponse(data=llm_out)


@router.delete("/{llm_id}", response_model=ApiResponse, summary="Delete LLM")
async def delete_llm(
    llm_id: int,
    svc: LLMService = Depends(get_service),
):

    await svc.delete_llm(llm_id)
    return ApiResponse()
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-05
# @description: FastAPI router for Domain management

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, Query, Request, status

from app.core.security.auth_permission import AuthPermission
from app.schemas.admin.domain import (
    DomainCreate,
    DomainUpdate
)
from app.services.admin.domain import DomainService
from app.schemas.common import ApiResponse

_list   = AuthPermission.Permission("domain:list")
_add    = AuthPermission.Permission("domain:add")
_edit   = AuthPermission.Permission("domain:edit")
_delete = AuthPermission.Permission("domain:delete")

router = APIRouter()

def get_service(request: Request) -> DomainService:
    return request.app.state.container.domain_service

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=ApiResponse,  # Change the response model to ApiResponse
    summary="List domains",
    description="Return a paginated list of all domains, optionally filtered by type.",
)
async def list_domains(
    type: Optional[str] = Query(None, description="Filter by domain type, e.g. 'law'"),
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    svc:       DomainService   = Depends(get_service),
    caller_id: int            = Depends(_list),
) -> ApiResponse:
    domains = await svc.list_domains(type_filter=type, page=page, page_size=page_size)
    return ApiResponse(data=domains)


@router.get(
    "/{domain_id}",
    response_model=ApiResponse,
    summary="Get domain by id",
)
async def get_domain(
    domain_id: int, 
    svc:       DomainService   = Depends(get_service),
    caller_id: int            = Depends(_list),
) -> ApiResponse:
    domain = await svc.get_domain(domain_id)
    return ApiResponse(data=domain)


@router.post(
    "",
    response_model=ApiResponse,    
    summary="Create a new domain",
)
async def create_domain(
    payload: DomainCreate, 
    svc:       DomainService   = Depends(get_service),
    caller_id: int            = Depends(_add),
) -> ApiResponse:
    domain = await svc.create_domain(payload)
    return ApiResponse(data=domain)


@router.patch(
    "/{domain_id}",
    response_model=ApiResponse,
    summary="Partially update a domain",
)
async def update_domain(
    domain_id: int,
    payload: DomainUpdate,
    svc:       DomainService   = Depends(get_service),
    caller_id: int            = Depends(_edit),
) -> ApiResponse:
    domain = await svc.update_domain(domain_id, payload)
    return ApiResponse(data=domain)


@router.delete(
    "/{domain_id}",
    summary="Delete a domain",
)
async def delete_domain(
    domain_id: int, 
    svc:       DomainService   = Depends(get_service),
    caller_id: int            = Depends(_delete),
) -> ApiResponse:
    await svc.delete_domain(domain_id)
    return ApiResponse(message="Domain deleted successfully")


@router.post("/bulk-delete", summary="Bulk delete domains")
async def bulk_delete_tools(
    ids: list[int],
    svc:       DomainService   = Depends(get_service),
    caller_id: int            = Depends(_delete),
):
    deleted = await svc.bulk_delete(ids)
    return ApiResponse(data={"deleted": deleted})

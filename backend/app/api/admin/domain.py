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
    DomainListResponse,
    DomainRead,
    DomainUpdate
)
from app.services.admin.domain import DomainService

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
    response_model=DomainListResponse,
    summary="List domains",
    description="Return a paginated list of all domains, optionally filtered by type.",
)
async def list_domains(
    type: Optional[str] = Query(None, description="Filter by domain type, e.g. 'law'"),
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    svc:       DomainService   = Depends(get_service),
    caller_id: int            = Depends(_list),
) -> DomainListResponse:
    return await svc.list_domains(type_filter=type, page=page, page_size=page_size)


@router.get(
    "/{domain_id}",
    response_model=DomainRead,
    summary="Get domain by id",
)
async def get_domain(
    domain_id: int, 
    svc:       DomainService   = Depends(get_service),
    caller_id: int            = Depends(_list),
) -> DomainRead:
    return await svc.get_domain(domain_id)


@router.post(
    "",
    response_model=DomainRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new domain",
)
async def create_domain(
    payload: DomainCreate, 
    svc:       DomainService   = Depends(get_service),
    caller_id: int            = Depends(_add),
) -> DomainRead:
    return await svc.create_domain(payload)


@router.patch(
    "/{domain_id}",
    response_model=DomainRead,
    summary="Partially update a domain",
)
async def update_domain(
    domain_id: int,
    payload: DomainUpdate,
    svc:       DomainService   = Depends(get_service),
    caller_id: int            = Depends(_edit),
) -> DomainRead:
    return await svc.update_domain(domain_id, payload)


@router.delete(
    "/{domain_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a domain",
)
async def delete_domain(
    domain_id: int, 
    svc:       DomainService   = Depends(get_service),
    caller_id: int            = Depends(_delete),
) -> None:
    await svc.delete_domain(domain_id)

@router.post("/bulk-delete", status_code=status.HTTP_200_OK, summary="Bulk delete domains")
async def bulk_delete_tools(
    ids: list[int],
    svc:       DomainService   = Depends(get_service),
    caller_id: int            = Depends(_delete),
):
    deleted = await svc.bulk_delete(ids)
    return {"deleted": deleted}

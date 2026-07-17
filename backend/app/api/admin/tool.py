#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-04
# @description: Tool/Skill API Router – HTTP layer only

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.core.security.auth_permission import AuthPermission
from app.schemas.common import ApiResponse, PageResult
from app.schemas.admin.tool import ToolCreate, ToolRead, ToolUpdate
from app.services.admin.tool import ToolService

router = APIRouter()

# ──────────────────────────────────────────────
# Service dependency
# ──────────────────────────────────────────────

def get_service(request: Request) -> ToolService:
    return request.app.state.container.tool_service

_list   = AuthPermission.Permission("tool:list")
_add    = AuthPermission.Permission("tool:add")
_edit   = AuthPermission.Permission("tool:edit")
_delete = AuthPermission.Permission("tool:delete")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=ApiResponse, summary="List tools (paginated)")
async def list_tools(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tool_type: str | None = Query(None),
    is_active: bool | None = Query(None),
    keyword: str | None = Query(None),
    svc:       ToolService   = Depends(get_service),
    caller_id: int            = Depends(_list),
):
    total, items = await svc.list(
        page=page,
        page_size=page_size,
        tool_type=tool_type,
        is_active=is_active,
        keyword=keyword,
    )
    result = PageResult[ToolRead](total=total, page=page, page_size=page_size, data=items)
    return ApiResponse(data=result)


@router.get("/stats", response_model=ApiResponse, summary="Aggregate stats")
async def get_stats(
    svc:       ToolService   = Depends(get_service),
    caller_id: int            = Depends(_list),
):
    stats = await svc.stats()
    return await ApiResponse(data=stats)


@router.get("/{tool_id}", response_model=ApiResponse, summary="Get a single tool")
async def get_tool(
    tool_id: int,
    svc:       ToolService   = Depends(get_service),
    caller_id: int            = Depends(_list),
):
    tool = await svc.get(tool_id)
    return ApiResponse(data=tool)

@router.post("", response_model=ApiResponse, summary="Create tool")
async def create_tool(
    payload: ToolCreate,
    svc:       ToolService   = Depends(get_service),
    caller_id: int            = Depends(_add),
):
    tool= await svc.create(payload)
    return ApiResponse(data=tool)


@router.patch("/{tool_id}", response_model=ApiResponse, summary="Partially update tool")
async def update_tool(
    tool_id: int, 
    payload: ToolUpdate,
    svc:       ToolService   = Depends(get_service),
    caller_id: int            = Depends(_edit),
):

    tool = await svc.update(tool_id, payload)
    return ApiResponse(data=tool)


@router.patch("/{tool_id}/toggle", response_model=ApiResponse, summary="Toggle active status")
async def toggle_tool(
    tool_id: int,    
    svc:       ToolService   = Depends(get_service),
    caller_id: int            = Depends(_edit),
):
    await svc.toggle_active(tool_id)
    return ApiResponse()


@router.delete("/{tool_id}", response_model=ApiResponse, summary="Delete tool")
async def delete_tool(
    tool_id: int,
    svc:       ToolService   = Depends(get_service),
    caller_id: int            = Depends(_delete),
):

    deleted = await svc.delete(tool_id)
    return ApiResponse(data={"deleted": deleted})

@router.post("/bulk-delete", response_model=ApiResponse, summary="Bulk delete tools")
async def bulk_delete_tools(
    tool_ids: list[int],
    svc:       ToolService   = Depends(get_service),
    caller_id: int            = Depends(_delete),
):
    deleted = await svc.bulk_delete(tool_ids)
    return ApiResponse(data= {"deleted": deleted})

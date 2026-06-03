#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-04
# @description: Tool/Skill API Router – HTTP layer only

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.security.auth_permission import AuthPermission
from app.schemas.common import PageResult
from app.schemas.admin.tool import ToolCreate, ToolRead, ToolUpdate
from app.services.admin.tool import ToolNotFoundError, ToolService

router = APIRouter()

# ──────────────────────────────────────────────
# Service dependency
# ──────────────────────────────────────────────

def get_tool_service(request: Request) -> ToolService:
    return request.app.state.container.tool_service

_list   = AuthPermission.Permission("tool:list")
_add    = AuthPermission.Permission("tool:add")
_edit   = AuthPermission.Permission("tool:edit")
_delete = AuthPermission.Permission("tool:delete")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=PageResult, summary="List tools (paginated)")
async def list_tools(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tool_type: str | None = Query(None),
    is_active: bool | None = Query(None),
    keyword: str | None = Query(None),
    svc:       ToolService   = Depends(get_tool_service),
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
    return result


@router.get("/stats", response_model=dict[str, Any], summary="Aggregate stats")
async def get_stats(
    svc:       ToolService   = Depends(get_tool_service),
    caller_id: int            = Depends(_list),
):
    return await svc.stats()


@router.get("/{tool_id}", response_model=ToolRead, summary="Get a single tool")
async def get_tool(
    tool_id: int,
    svc:       ToolService   = Depends(get_tool_service),
    caller_id: int            = Depends(_list),
):
    tool = await svc.get(tool_id)
    if not tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    return tool


@router.post("", response_model=ToolRead, status_code=status.HTTP_201_CREATED, summary="Create tool")
async def create_tool(
    payload: ToolCreate,
    svc:       ToolService   = Depends(get_tool_service),
    caller_id: int            = Depends(_add),
):
    try:
        return await svc.create(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

@router.patch("/{tool_id}", response_model=ToolRead, summary="Partially update tool")
async def update_tool(
    tool_id: int, 
    payload: ToolUpdate,
    svc:       ToolService   = Depends(get_tool_service),
    caller_id: int            = Depends(_edit),
):
    try:
        tool = await svc.update(tool_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if not tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    return tool


@router.patch("/{tool_id}/toggle", response_model=ToolRead, summary="Toggle active status")
async def toggle_tool(
    tool_id: int, 
    is_active: bool = Query(...),
    svc:       ToolService   = Depends(get_tool_service),
    caller_id: int            = Depends(_edit),
):
    tool = await svc.toggle_active(tool_id, is_active)
    if not tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    return tool


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete tool")
async def delete_tool(
    tool_id: int,
    svc:       ToolService   = Depends(get_tool_service),
    caller_id: int            = Depends(_delete),
):
    try:
        await svc.delete(tool_id)
    except ToolNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")


@router.post("/bulk-delete", status_code=status.HTTP_200_OK, summary="Bulk delete tools")
async def bulk_delete_tools(
    tool_ids: list[int],
    svc:       ToolService   = Depends(get_tool_service),
    caller_id: int            = Depends(_delete),
):
    deleted = await svc.bulk_delete(tool_ids)
    return {"deleted": deleted}

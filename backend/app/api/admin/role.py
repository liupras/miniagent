#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-17 
# @description:  FastAPI routes for role management.

from fastapi import APIRouter, Depends, Query, Request

from app.core.security.auth_permission import AuthPermission
from app.schemas.admin.permission import RoleCreate, RoleMenuUpdate, RoleOption, RoleUpdate
from app.schemas.common import ApiResponse
from app.services.admin.role import RoleService

router = APIRouter()


def get_service(request: Request) -> RoleService:
    return request.app.state.container.role_service


_list = AuthPermission.Permission("role:list")
_add = AuthPermission.Permission("role:add")
_edit = AuthPermission.Permission("role:edit")
_delete = AuthPermission.Permission("role:delete")


@router.get("/options", response_model=ApiResponse, summary="Role dropdown options")
async def role_options(
    request: Request,
    caller_id: int = Depends(_list),
):
    roles = await request.app.state.container.role_db.options()
    return ApiResponse(data=[RoleOption.model_validate(role) for role in roles])


@router.get("", response_model=ApiResponse, summary="List roles")
async def list_roles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None),
    svc: RoleService = Depends(get_service),
    caller_id: int = Depends(_list),
):
    return ApiResponse(data=await svc.list(page, page_size, keyword))


@router.post("", response_model=ApiResponse, summary="Create role")
async def create_role(payload: RoleCreate, svc: RoleService = Depends(get_service), caller_id: int = Depends(_add)):
    return ApiResponse(data=await svc.create(payload))


@router.get("/{role_id}", response_model=ApiResponse, summary="Get role")
async def get_role(role_id: int, svc: RoleService = Depends(get_service), caller_id: int = Depends(_list)):
    return ApiResponse(data=await svc.get(role_id))


@router.patch("/{role_id}", response_model=ApiResponse, summary="Update role")
async def update_role(role_id: int, payload: RoleUpdate, svc: RoleService = Depends(get_service), caller_id: int = Depends(_edit)):
    return ApiResponse(data=await svc.update(role_id, payload))


@router.put("/{role_id}/menus", response_model=ApiResponse, summary="Replace role menu/button grants")
async def set_role_menus(role_id: int, payload: RoleMenuUpdate, svc: RoleService = Depends(get_service), caller_id: int = Depends(_edit)):
    return ApiResponse(data=await svc.set_menus(role_id, payload))


@router.delete("/{role_id}", response_model=ApiResponse, summary="Delete role")
async def delete_role(role_id: int, svc: RoleService = Depends(get_service), caller_id: int = Depends(_delete)):
    await svc.delete(role_id)
    return ApiResponse(data={"deleted": 1})

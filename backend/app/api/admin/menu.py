#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-17 
# @description: FastAPI routes for menu and button permission management.

from fastapi import APIRouter, Depends, Query, Request

from app.core.security.auth_permission import AuthPermission
from app.schemas.admin.permission import MenuType
from app.schemas.common import ApiResponse
from app.services.admin.menu import MenuService

router = APIRouter()


def get_service(request: Request) -> MenuService:
    return request.app.state.container.menu_service


_list = AuthPermission.Permission("menu:list")
#_add = AuthPermission.Permission("menu:add")
#_edit = AuthPermission.Permission("menu:edit")
#_delete = AuthPermission.Permission("menu:delete")


@router.get("", response_model=ApiResponse, summary="List menus/buttons as tree or flat list")
async def list_menus(
    tree: bool = Query(True),
    menu_type: MenuType | None = Query(None),
    is_active: bool | None = Query(None),
    svc: MenuService = Depends(get_service),
    caller_id: int = Depends(_list),
):
    return ApiResponse(data=await svc.list(tree, menu_type, is_active))

@router.get("/{menu_id}", response_model=ApiResponse, summary="Get menu/button")
async def get_menu(menu_id: int, svc: MenuService = Depends(get_service), caller_id: int = Depends(_list)):
    return ApiResponse(data=await svc.get(menu_id))

'''
@router.post("", response_model=ApiResponse, summary="Create menu/button")
async def create_menu(payload: MenuCreate, svc: MenuService = Depends(get_service), caller_id: int = Depends(_add)):
    return ApiResponse(data=await svc.create(payload))

@router.patch("/{menu_id}", response_model=ApiResponse, summary="Update menu/button")
async def update_menu(menu_id: int, payload: MenuUpdate, svc: MenuService = Depends(get_service), caller_id: int = Depends(_edit)):
    return ApiResponse(data=await svc.update(menu_id, payload))

@router.delete("/{menu_id}", response_model=ApiResponse, summary="Delete menu/button and descendants")
async def delete_menu(menu_id: int, svc: MenuService = Depends(get_service), caller_id: int = Depends(_delete)):
    await svc.delete(menu_id)
    return ApiResponse(data={"deleted": 1})
'''
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-30 
# @description: FastAPI routes for administrative user management.

from fastapi import APIRouter, Depends, Query, Request

from app.core.security.auth_permission import AuthPermission
from app.schemas.admin.user import (
    UserCreate, UserListParams, UserPasswordReset, UserRoleUpdate, UserUpdate,
)
from app.schemas.common import ApiResponse
from app.services.admin.user import UserService

router = APIRouter()


def get_service(request: Request) -> UserService:
    return request.app.state.container.user_service


_list = AuthPermission.Permission("user:list")
_add = AuthPermission.Permission("user:add")
_edit = AuthPermission.Permission("user:edit")
_delete = AuthPermission.Permission("user:delete")


@router.get("/options", response_model=ApiResponse, summary="User dropdown options")
async def get_user_options(
    is_active: bool | None = Query(True),
    svc: UserService = Depends(get_service),
    caller_id: int = Depends(_list),
):
    return ApiResponse(data=await svc.get_options(is_active))


@router.get("", response_model=ApiResponse, summary="List users")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None),
    username: str | None = Query(None),
    is_active: bool | None = Query(None),
    role_id: int | None = Query(None),
    svc: UserService = Depends(get_service),
    caller_id: int = Depends(_list),
):
    params = UserListParams(
        page=page, page_size=page_size, keyword=keyword, username=username,
        is_active=is_active, role_id=role_id,
    )
    return ApiResponse(data=await svc.list_users(params))


@router.post("", response_model=ApiResponse, summary="Create user")
async def create_user(
    payload: UserCreate,
    svc: UserService = Depends(get_service),
    caller_id: int = Depends(_add),
):
    return ApiResponse(data=await svc.create(payload))


@router.get("/by-username/{username}", response_model=ApiResponse, summary="Get user by username")
async def get_user_by_username(
    username: str,
    svc: UserService = Depends(get_service),
    caller_id: int = Depends(_list),
):
    return ApiResponse(data=await svc.get_user(username))


@router.get("/{user_id}", response_model=ApiResponse, summary="Get user")
async def get_user(
    user_id: int,
    svc: UserService = Depends(get_service),
    caller_id: int = Depends(_list),
):
    return ApiResponse(data=await svc.get_user_by_id(user_id))


@router.patch("/{user_id}", response_model=ApiResponse, summary="Update user profile or status")
async def update_user(
    user_id: int,
    payload: UserUpdate,
    svc: UserService = Depends(get_service),
    caller_id: int = Depends(_edit),
):
    return ApiResponse(data=await svc.update(user_id, payload))


@router.put("/{user_id}/roles", response_model=ApiResponse, summary="Replace user roles")
async def assign_user_roles(
    user_id: int,
    payload: UserRoleUpdate,
    svc: UserService = Depends(get_service),
    caller_id: int = Depends(_edit),
):
    return ApiResponse(data=await svc.assign_roles(user_id, payload.role_ids))


@router.put("/{user_id}/password", response_model=ApiResponse, summary="Reset user password")
async def reset_user_password(
    user_id: int,
    payload: UserPasswordReset,
    svc: UserService = Depends(get_service),
    caller_id: int = Depends(_edit),
):
    await svc.reset_password(user_id, payload.password)
    return ApiResponse()


@router.delete("/{user_id}", response_model=ApiResponse, summary="Delete user")
async def delete_user(
    user_id: int,
    svc: UserService = Depends(get_service),
    caller_id: int = Depends(_delete),
):
    await svc.delete(user_id)
    return ApiResponse(data={"deleted": 1})

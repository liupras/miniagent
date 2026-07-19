#!/usr/bin/python
# -*- coding:utf-8 -*-

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from app.core.security.auth_permission import AuthPermission
from app.schemas.admin.system_setting import SystemSettingUpdate
from app.schemas.common import ApiResponse
from app.services.admin.system_setting import SystemSettingService

router = APIRouter()

_list = AuthPermission.Permission("system_setting:list")
_edit = AuthPermission.Permission("system_setting:edit")


def get_service(request: Request) -> SystemSettingService:
    return request.app.state.container.setting_service


@router.get("", response_model=ApiResponse, summary="List system settings")
async def list_system_settings(
    group: Optional[str] = Query(None, max_length=50),
    service: SystemSettingService = Depends(get_service),
    caller_id: int = Depends(_list),
):
    return ApiResponse(data=await service.list_settings(group))


@router.get("/{key}", response_model=ApiResponse, summary="Get system setting")
async def get_system_setting(
    key: str,
    service: SystemSettingService = Depends(get_service),
    caller_id: int = Depends(_list),
):
    return ApiResponse(data=await service.get_setting(key))


@router.patch("/{key}", response_model=ApiResponse, summary="Update system setting")
async def update_system_setting(
    key: str,
    payload: SystemSettingUpdate,
    service: SystemSettingService = Depends(get_service),
    caller_id: int = Depends(_edit),
):
    return ApiResponse(data=await service.update_setting(key, payload))

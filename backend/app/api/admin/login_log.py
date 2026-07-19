#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-19
# @description: Login Log

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from app.core.security.auth_permission import AuthPermission
from app.schemas.common import ApiResponse
from app.services.admin.login_log import LoginLogAdminService

router = APIRouter()

_list = AuthPermission.Permission("login_log:list")


def get_service(request: Request) -> LoginLogAdminService:
    return request.app.state.container.login_log_admin_service


@router.get("", response_model=ApiResponse, summary="Paginated login log list")
async def list_login_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, max_length=200),
    request_id: Optional[str] = Query(None, max_length=36),
    user_id: Optional[int] = Query(None, ge=1),
    username: Optional[str] = Query(None, max_length=100),
    ip_address: Optional[str] = Query(None, max_length=50),
    event_type: Optional[str] = Query(None, pattern="^(LOGIN|REFRESH_TOKEN)$"),
    success: Optional[bool] = Query(None),
    created_from: Optional[datetime] = Query(None),
    created_to: Optional[datetime] = Query(None),
    service: LoginLogAdminService = Depends(get_service),
    caller_id: int = Depends(_list),
):
    return ApiResponse(
        data=await service.list_logs(
            page=page,
            page_size=page_size,
            keyword=keyword,
            request_id=request_id,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            event_type=event_type,
            success=success,
            created_from=created_from,
            created_to=created_to,
        )
    )


@router.get("/{login_log_id}", response_model=ApiResponse, summary="Get login log")
async def get_login_log(
    login_log_id: int,
    service: LoginLogAdminService = Depends(get_service),
    caller_id: int = Depends(_list),
):
    return ApiResponse(data=await service.get(login_log_id))

#!/usr/bin/python
# -*- coding:utf-8 -*-

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from app.core.security.auth_permission import AuthPermission
from app.schemas.common import ApiResponse
from app.services.admin.audit_log import AuditLogService

router = APIRouter()

_list = AuthPermission.Permission("audit_log:list")


def get_service(request: Request) -> AuditLogService:
    return request.app.state.container.audit_log_service


@router.get("", response_model=ApiResponse, summary="Paginated audit log list")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, max_length=200),
    request_id: Optional[str] = Query(None, max_length=36),
    user_id: Optional[int] = Query(None, ge=1),
    username: Optional[str] = Query(None, max_length=100),
    target_type: Optional[str] = Query(None, max_length=50),
    target_id: Optional[str] = Query(None, max_length=100),
    action: Optional[str] = Query(None, max_length=20),
    status: Optional[str] = Query(None, max_length=20),
    created_from: Optional[datetime] = Query(None),
    created_to: Optional[datetime] = Query(None),
    service: AuditLogService = Depends(get_service),
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
            target_type=target_type,
            target_id=target_id,
            action=action,
            status=status,
            created_from=created_from,
            created_to=created_to,
        )
    )


@router.get("/{audit_id}", response_model=ApiResponse, summary="Get audit log")
async def get_audit_log(
    audit_id: int,
    service: AuditLogService = Depends(get_service),
    caller_id: int = Depends(_list),
):
    return ApiResponse(data=await service.get(audit_id))

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-30
# @description: User API Router – HTTP layer only

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.schemas.common import PageResult, ApiResponse
from app.schemas.admin.user import UserListParams, UserOptionItem, UserOut
from app.services.admin.user import UserService, UserNotFoundError
from app.core.service_container import ServiceContainer

router = APIRouter()

# ──────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────

def get_container(request: Request) -> ServiceContainer:
    return request.app.state.container

def get_user_service(
    container: ServiceContainer = Depends(get_container),
) -> UserService:
    return container.user_service

# ──────────────────────────────────────────────
# Exception → HTTP helper
# ──────────────────────────────────────────────

def _raise_not_found(exc: UserNotFoundError) -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@router.get(
    "/options",
    response_model=ApiResponse,
    summary="User dropdown options (id + username + nickname)",
)
async def get_user_options(
    is_active: Optional[bool] = Query(
        True,
        description="Filter by active status. "
                    "Pass `true` (default) for active-only, "
                    "`false` for inactive-only, "
                    "omit the param entirely for all users.",
    ),
    svc: UserService = Depends(get_user_service),
):
    """
    Lightweight endpoint consumed by frontend selectors (e.g. Agent form).
    Returns id, username, nickname for every matching user, ordered by username.

    Default behaviour: only active users are returned.
    """
    options: List[UserOptionItem] = await svc.get_options(is_active=is_active)
    result = ApiResponse(data=options)
    return result

@router.get(
    "",
    response_model=ApiResponse,
    summary="Paginated user list with roles and permissions",
)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    username: Optional[str] = Query(None, description="Fuzzy filter by username"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    svc: UserService = Depends(get_user_service),
):
    params = UserListParams(
        page=page,
        page_size=page_size,
        username=username,
        is_active=is_active,
    )
    result: PageResult[UserOut] = await svc.list_users(params)
    return ApiResponse(data=result)


@router.get(
    "/{username}",
    response_model=ApiResponse,
    summary="Get full user info by username",
)
async def get_user(
    username: str,
    svc: UserService = Depends(get_user_service),
):
    try:
        user_out = await svc.get_user(username)
    except UserNotFoundError as exc:
        _raise_not_found(exc)
    return ApiResponse(data=user_out)
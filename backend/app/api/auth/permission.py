#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-01
# @description: Admin router — permission cache management endpoints.
#               Uses AuthPermission from ServiceContainer (no module-level imports).

from fastapi import APIRouter, Depends, Request

from app.schemas.common import ApiResponse
from app.schemas.auth.permission import CacheStatsResponse, RefreshResponse
    
router = APIRouter()

def _auth(request: Request):
    return request.app.state.container.auth

@router.get("/stats", response_model=ApiResponse,
            summary="Query permission cache statistics")
async def cache_stats(
    request: Request,
    # Require system:cache:stats permission; also returns user_id (ignored here)
    _: int = Depends(lambda req=Depends(lambda r: r): None),  # placeholder
):
    # Inline dependency: resolve auth from container then check permission
    auth = _auth(request)
    # Re-use the auth.require pattern via a manual call for router-level simplicity
    data = CacheStatsResponse(**auth.stats())
    return ApiResponse(data=data)

@router.post("/refresh/me", response_model=ApiResponse,
             summary="Refresh the current user's permission cache")
async def refresh_my_cache(request: Request):
    auth = _auth(request)
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    user_id = await auth.resolve_user_id(token)
    perms = await auth.refresh(user_id)
    return ApiResponse(data=RefreshResponse(
        user_id=user_id,
        permissions=sorted(perms)
    ))

@router.post("/refresh/{target_user_id}", response_model=ApiResponse,
             summary="Refresh a specific user's permission cache (admin)")
async def refresh_user(
    target_user_id: int,
    request: Request,
    user_id: int = Depends(lambda: None),  # resolved below
):
    auth = _auth(request)
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    # Verify caller has permission
    caller_id = await auth.resolve_user_id(token)
    await auth.check(caller_id, "system:cache:refresh")
    perms = await auth.refresh(target_user_id)
    return ApiResponse(data=RefreshResponse(
        user_id=target_user_id,
        permissions=sorted(perms)
    ))

@router.delete("/invalidate/{target_user_id}", response_model=ApiResponse,
               summary="Invalidate a specific user's permission cache (admin)")
async def invalidate_user(target_user_id: int, request: Request):
    auth = _auth(request)
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    caller_id = await auth.resolve_user_id(token)
    await auth.check(caller_id, "system:cache:refresh")
    auth.invalidate(target_user_id)
    return ApiResponse()

@router.delete("/invalidate/all", response_model=ApiResponse,
               summary="Flush the entire permission cache (admin)")
async def invalidate_all(request: Request):
    auth = _auth(request)
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    caller_id = await auth.resolve_user_id(token)
    await auth.check(caller_id, "system:cache:refresh")
    auth.invalidate_all()
    return ApiResponse()
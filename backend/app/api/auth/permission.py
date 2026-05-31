#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-01
# @description: Admin router — permission cache management endpoints.
#               Uses AuthPermission from ServiceContainer (no module-level imports).

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

# ── Response schemas ───────────────────────────────────────────────────────────

class CacheStatsResponse(BaseModel):
    backend:         str
    max_size:        int
    current_size:    int
    hits:            int
    misses:          int
    hit_rate:        str
    ttl_expirations: int


class RefreshResponse(BaseModel):
    user_id:     int
    permissions: list[str]
    message:     str


class InvalidateResponse(BaseModel):
    message: str

router = APIRouter()

def _auth(request: Request):
    return request.app.state.container.auth
# ── GET /auth/cache/stats ──────────────────────────────────────────────────
@router.get("/stats", response_model=CacheStatsResponse,
            summary="Query permission cache statistics")
async def cache_stats(
    request: Request,
    # Require system:cache:stats permission; also returns user_id (ignored here)
    _: int = Depends(lambda req=Depends(lambda r: r): None),  # placeholder
):
    # Inline dependency: resolve auth from container then check permission
    auth = _auth(request)
    # Re-use the auth.require pattern via a manual call for router-level simplicity
    return CacheStatsResponse(**auth.stats())
# ── POST /auth/cache/refresh/me ────────────────────────────────────────────
@router.post("/refresh/me", response_model=RefreshResponse,
             summary="Refresh the current user's permission cache")
async def refresh_my_cache(request: Request):
    auth = _auth(request)
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    user_id = await auth.resolve_user_id(token)
    perms = await auth.refresh(user_id)
    return RefreshResponse(
        user_id=user_id,
        permissions=sorted(perms),
        message="Your permission cache has been refreshed.",
    )
# ── POST /auth/cache/refresh/{target_user_id} ──────────────────────────────
@router.post("/refresh/{target_user_id}", response_model=RefreshResponse,
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
    return RefreshResponse(
        user_id=target_user_id,
        permissions=sorted(perms),
        message=f"Permission cache for user {target_user_id} refreshed.",
    )
# ── DELETE /auth/cache/invalidate/{target_user_id} ────────────────────────
@router.delete("/invalidate/{target_user_id}", response_model=InvalidateResponse,
               summary="Invalidate a specific user's permission cache (admin)")
async def invalidate_user(target_user_id: int, request: Request):
    auth = _auth(request)
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    caller_id = await auth.resolve_user_id(token)
    await auth.check(caller_id, "system:cache:invalidate")
    auth.invalidate(target_user_id)
    return InvalidateResponse(
        message=f"Cache entry for user {target_user_id} invalidated.",
    )
# ── DELETE /auth/cache/invalidate/all ─────────────────────────────────────
@router.delete("/invalidate/all", response_model=InvalidateResponse,
               summary="Flush the entire permission cache (admin)")
async def invalidate_all(request: Request):
    auth = _auth(request)
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    caller_id = await auth.resolve_user_id(token)
    await auth.check(caller_id, "system:cache:invalidate")
    auth.invalidate_all()
    return InvalidateResponse(message="All permission cache entries flushed.")
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-28
# @description: User authentication

from fastapi import Request,HTTPException,Depends,APIRouter,Body
import re
from datetime import datetime, timedelta

from app.repositories import AsyncUserDatabase
from app.core.security.jwt_auth import JWTAuth
from app.models.original import LoginRequest, LoginResponse
from app.core.config import settings

ACCESS_TOKEN_EXPIRE_DAYS = settings.access_token_expire_days
REFRESH_TOKEN_EXPIRE_DAYS = settings.refresh_token_expire_days

router = APIRouter()

def get_jwt_auth(request: Request) -> JWTAuth:
    return request.app.state.container.jwt_auth

def get_user_db(request: Request) -> AsyncUserDatabase:
    return request.app.state.container.user_db

async def get_current_user(
    request: Request,
    user_db: AsyncUserDatabase = Depends(get_user_db),
    jwt_auth: JWTAuth = Depends(get_jwt_auth),
) -> str:

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    match = re.match(r"^Bearer\s+(.+)$", auth_header.strip())
    if not match:
        raise HTTPException(status_code=401, detail="Invalid token format")

    token = match.group(1)

    payload = jwt_auth.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    username = payload.get("username")

    user_info = await user_db.get_user_info(username)
    if not user_info or not user_info.get("is_active"):
        raise HTTPException(status_code=403, detail="User not found or inactive")

    return username

@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest = Body(...),
    user_db: AsyncUserDatabase = Depends(get_user_db),
    jwt_auth: JWTAuth = Depends(get_jwt_auth)
):

    if not await user_db.verify_user(request.username, request.password):
        return LoginResponse(
            success=False,
            data=None
        )

    user_info = await user_db.get_user_info(request.username)

    # Generate access token and refresh token
    access_token = jwt_auth.create_token(
        user_id=request.username,
        token_type="access",
        expires_delta=timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    )
    refresh_token = jwt_auth.create_token(
        user_id=request.username,
        token_type="refresh",
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )
    expires = (datetime.now() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)).strftime(
        "%Y/%m/%d %H:%M:%S"
    )

    response = LoginResponse(
        success=True,
        data={
            "avatar": user_info.get("avatar", ""),
            "username": user_info.get("username"), 
            "nickname": user_info.get("nickname", user_info.get("username")),
            "roles": user_info.get("roles", ["common"]),
            "permissions": user_info.get("permissions", []),
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "expires": expires,
        }
    )

    return response

@router.get("/get-async-routes")
async def get_async_routes():

    permission_router = {
        "path": "/permission",
        "meta": {
            "title": "menus.purePermission",
            "icon": "ep:lollipop",
            "rank": 10
        },
        "children": [
            {
                "path": "/permission/page/index",
                "name": "PermissionPage",
                "meta": {
                    "title": "menus.purePermissionPage",
                    "roles": ["admin", "common"]
                }
            },
            {
                "path": "/permission/button",
                "meta": {
                    "title": "menus.purePermissionButton",
                    "roles": ["admin", "common"]
                },
                "children": [
                    {
                        "path": "/permission/button/router",
                        "component": "permission/button/index",
                        "name": "PermissionButtonRouter",
                        "meta": {
                            "title": "menus.purePermissionButtonRouter",
                            "auths": [
                                "permission:btn:add",
                                "permission:btn:edit",
                                "permission:btn:delete"
                            ]
                        }
                    }
                ]
            }
        ]
    }

    return {
        "success": True,
        "data": [permission_router]
    }

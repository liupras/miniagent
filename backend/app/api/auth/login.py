#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-28
# @description: User authentication

from fastapi import Request,Depends,APIRouter,Body
from datetime import datetime, timedelta

from app.core.security.jwt_auth import JWTAuth
from app.schemas.auth.login import LoginRequest, LoginResponse,RefreshTokenRequest
from app.core.config import settings
from app.services.admin.user import UserService

ACCESS_TOKEN_EXPIRE_DAYS = settings.access_token_expire_days
REFRESH_TOKEN_EXPIRE_DAYS = settings.refresh_token_expire_days

router = APIRouter()

def get_jwt_auth(request: Request) -> JWTAuth:
    return request.app.state.container.jwt_auth

def get_user_service(request: Request) -> UserService:
    return request.app.state.container.user_service

@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest = Body(...),
    user_service: UserService = Depends(get_user_service),
    jwt_auth: JWTAuth = Depends(get_jwt_auth)
):

    if not await user_service.verify_user(request.username, request.password):
        res = LoginResponse(
            success=False,
            data=None
        )
        return res

    user_info = await user_service.get_user(request.username)

    # Generate access token and refresh token
    access_token = jwt_auth.create_token(
        username=request.username,
        token_type="access",
        expires_delta=timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    )
    refresh_token = jwt_auth.create_token(
        username=request.username,
        token_type="refresh",
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )
    expires = (datetime.now() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)).strftime(
        "%Y/%m/%d %H:%M:%S"
    )

    res = LoginResponse(
        success=True,
        data={
            "avatar": user_info.avatar,
            "username": user_info.username, 
            "nickname": user_info.nickname,
            "roles": user_info.roles,
            "permissions": user_info.permissions,
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "expires": expires,
        }
    )

    return res

@router.post("/refresh-token", response_model=LoginResponse)
async def refresh_token(
    request: RefreshTokenRequest = Body(...),
    jwt_auth: JWTAuth = Depends(get_jwt_auth)
):

    if not request.refreshToken:
        return LoginResponse(success=False, data={})

    token_data = jwt_auth.decode_token(request.refreshToken)
    if not token_data or token_data.get("token_type") != "refresh":
        return LoginResponse(success=False, data={})

    username = token_data.get("username")

    new_access_token = jwt_auth.create_token(
        username=username,
        token_type="access",
        expires_delta=timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    )
    new_refresh_token = jwt_auth.create_token(
        username=username,
        token_type="refresh",
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )

    expires = (datetime.now() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)).strftime(
        "%Y/%m/%d %H:%M:%S"
    )

    # 4. 返回符合 ApiResponse 包装的结果
    return LoginResponse(
        success=True,
        data={
            "accessToken": new_access_token,
            "refreshToken": new_refresh_token,
            "expires": expires,
        }
    )
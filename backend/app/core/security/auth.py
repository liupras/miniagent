#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-28
# @description: User authentication

from fastapi import Request,Depends,APIRouter,Body
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
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-23
# @description: dependency injection for FastAPI routes, including JWT authentication and user retrieval.

from fastapi import Request,HTTPException,Depends
import re

from app.repositories import AsyncUserDatabase
from app.core.security.jwt_auth import JWTAuth

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

    username = jwt_auth.verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
  
    user_info = await user_db.get_user_info(username)
    if not user_info or not user_info.get("is_active"):
        raise HTTPException(status_code=403, detail="User not found or inactive")

    return username
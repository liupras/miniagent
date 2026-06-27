#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-23
# @description: dependency injection for FastAPI routes, including JWT authentication and user retrieval.

from fastapi import Request,HTTPException,Depends
import re

from app.core.i18n.i18n_http import raise_forbidden, raise_unauthorized
from app.repositories import AsyncUserDatabase
from app.core.security.jwt_auth import jwt_auth

def get_user_db(request: Request) -> AsyncUserDatabase:
    return request.app.state.container.user_db

async def get_current_user(
    request: Request,
    user_db: AsyncUserDatabase = Depends(get_user_db)
) -> str:

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise_unauthorized("auth.missing_auth_header")

    match = re.match(r"^Bearer\s+(.+)$", auth_header.strip())
    if not match:
        raise_unauthorized("auth.invalid_token_format")

    token = match.group(1)

    username = jwt_auth.verify_token(token)
    if not username:
        raise_unauthorized("auth.token_invalid")
  
    user_info = await user_db.get_user_info(username)
    if not user_info or not user_info.get("is_active"):
        raise_forbidden("auth.user_inactive")

    return username
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-28
# @description: User authentication

from datetime import datetime, timedelta
from math import ceil
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Request, Response
from loguru import logger

from app.core.config import settings
from app.core.security.jwt_auth import jwt_auth
from app.core.i18n.i18n import t
from app.schemas.common import ApiResponse
from app.schemas.auth.login import (
    LoginRequest, LoginResponse, PasswordPolicyResponse, RefreshTokenRequest,
)
from app.services.admin.user import UserNotFoundError, UserService
from app.services.auth.login_log import LoginLogService

ACCESS_TOKEN_EXPIRE_DAYS = settings.access_token_expire_days
REFRESH_TOKEN_EXPIRE_DAYS = settings.refresh_token_expire_days

router = APIRouter()


@router.get("/password-policy", response_model=ApiResponse)
async def password_policy():
    return ApiResponse(
        data=PasswordPolicyResponse(
            min_length=settings.password_min_length,
            require_upper=settings.password_require_upper,
            require_lower=settings.password_require_lower,
            require_digit=settings.password_require_digit,
            require_special=settings.password_require_special,
        )
    )


def get_user_service(request: Request) -> UserService:
    return request.app.state.container.user_service


def get_login_log_service(request: Request) -> LoginLogService:
    return request.app.state.container.login_log_service


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


async def _record_login_log_safely(
    service: LoginLogService,
    *,
    request_id: str,
    event_type: str,
    success: bool,
    request: Request,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    failure_reason: Optional[str] = None,
) -> None:
    values = {
        "request_id": request_id,
        "event_type": event_type,
        "success": success,
        "user_id": user_id,
        "username": username,
        "ip_address": _client_ip(request),
        "user_agent": request.headers.get("user-agent"),
        "failure_reason": failure_reason,
    }
    request.state.login_log_payload = values
    request.state.login_request_id = request_id
    recorded = False
    try:
        await service.record(**values)
        recorded = True
    except Exception as exc:
        logger.exception(f"Login log write failed: {exc}")
    finally:
        request.state.login_log_recorded = recorded


@router.post("/login", response_model=LoginResponse)
async def login(
    http_request: Request,
    response: Response,
    payload: LoginRequest = Body(...),
    user_service: UserService = Depends(get_user_service),
    login_log_service: LoginLogService = Depends(get_login_log_service),
):
    request_id = str(uuid4())
    http_request.state.login_request_id = request_id
    response.headers["X-Request-ID"] = request_id
    success = False
    failure_reason: Optional[str] = "invalid_credentials"
    user_id: Optional[int] = None

    try:
        auth_result = await user_service.authenticate(payload.username, payload.password)
        user_id = auth_result.user_id
        if auth_result.status == "locked":
            failure_reason = "account_locked"
            remaining_minutes = max(
                1,
                ceil((auth_result.locked_until - datetime.now()).total_seconds() / 60),
            )
            return LoginResponse(
                success=False,
                data=None,
                error_code="account_locked",
                message=t("auth.account_locked", minutes=remaining_minutes),
                locked_until=auth_result.locked_until,
            )
        if auth_result.status != "success":
            return LoginResponse(
                success=False,
                data=None,
                error_code="invalid_credentials",
                message=t("auth.login_failed"),
            )

        user_info = await user_service.get_user(payload.username)
        user_id = user_info.id

        access_token = jwt_auth.create_token(
            username=payload.username,
            token_type="access",
            expires_delta=timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS),
        )
        refresh_token = jwt_auth.create_token(
            username=payload.username,
            token_type="refresh",
            expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )
        expires = (datetime.now() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)).strftime(
            "%Y/%m/%d %H:%M:%S"
        )

        success = True
        failure_reason = None
        return LoginResponse(
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
            },
        )
    except Exception:
        failure_reason = "internal_error"
        raise
    finally:
        await _record_login_log_safely(
            login_log_service,
            request_id=request_id,
            event_type="LOGIN",
            success=success,
            request=http_request,
            user_id=user_id,
            username=payload.username,
            failure_reason=failure_reason,
        )


@router.post("/refresh-token", response_model=LoginResponse)
async def refresh_token(
    http_request: Request,
    response: Response,
    payload: RefreshTokenRequest = Body(...),
    user_service: UserService = Depends(get_user_service),
    login_log_service: LoginLogService = Depends(get_login_log_service),
):
    request_id = str(uuid4())
    http_request.state.login_request_id = request_id
    response.headers["X-Request-ID"] = request_id
    success = False
    failure_reason: Optional[str] = "missing_refresh_token"
    username: Optional[str] = None
    user_id: Optional[int] = None

    try:
        if not payload.refreshToken:
            return LoginResponse(success=False, data=None)

        token_data = jwt_auth.decode_token(payload.refreshToken, verify=True)
        if not token_data or token_data.get("type") != "refresh":
            failure_reason = "invalid_refresh_token"
            return LoginResponse(success=False, data=None)

        username = token_data.get("sub")
        if not username:
            failure_reason = "invalid_refresh_token"
            return LoginResponse(success=False, data=None)

        try:
            user_info = await user_service.get_user(username)
        except UserNotFoundError:
            failure_reason = "user_not_found"
            return LoginResponse(success=False, data=None)
        if not user_info.is_active:
            failure_reason = "user_disabled"
            return LoginResponse(success=False, data=None)
        user_id = user_info.id

        new_access_token = jwt_auth.create_token(
            username=username,
            token_type="access",
            expires_delta=timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS),
        )
        new_refresh_token = jwt_auth.create_token(
            username=username,
            token_type="refresh",
            expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )
        expires = (datetime.now() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)).strftime(
            "%Y/%m/%d %H:%M:%S"
        )

        success = True
        failure_reason = None
        return LoginResponse(
            success=True,
            data={
                "accessToken": new_access_token,
                "refreshToken": new_refresh_token,
                "expires": expires,
            },
        )
    except Exception:
        failure_reason = "internal_error"
        raise
    finally:
        await _record_login_log_safely(
            login_log_service,
            request_id=request_id,
            event_type="REFRESH_TOKEN",
            success=success,
            request=http_request,
            user_id=user_id,
            username=username,
            failure_reason=failure_reason,
        )

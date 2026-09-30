#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: Bearer authentication for VirtualCourt integration endpoints.

from __future__ import annotations

from typing import Annotated

from fastapi import Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.services.integration_auth import authenticate_internal_service_token


internal_service_bearer = HTTPBearer(
    auto_error=False,
    description="Bearer token shared by VirtualCourt internal services.",
)


def require_internal_service_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(internal_service_bearer),
    ],
) -> None:
    provided_token = (
        credentials.credentials
        if credentials is not None and credentials.scheme.casefold() == "bearer"
        else None
    )
    authenticate_internal_service_token(
        provided_token=provided_token,
        expected_token=(
            settings.virtual_court_internal_service_token.get_secret_value()
        ).strip(),
    )

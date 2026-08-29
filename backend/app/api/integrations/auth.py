#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: API-key authentication for VirtualCourt integration endpoints.

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Security
from fastapi.security import APIKeyHeader

from app.core.config import settings
from app.schemas.integrations.virtual_court import IntegrationErrorCode

from .errors import IntegrationAPIError


INTEGRATION_KEY_HEADER = "X-Integration-Key"
integration_key_header = APIKeyHeader(
    name=INTEGRATION_KEY_HEADER,
    auto_error=False,
    description="Static API key configured for the VirtualCourt integration.",
)


def require_virtual_court_api_key(
    provided_key: Annotated[str | None, Security(integration_key_header)],
) -> None:
    expected_key = settings.virtual_court_api_key.get_secret_value()
    if not expected_key:
        raise IntegrationAPIError(
            status_code=503,
            code=IntegrationErrorCode.SERVICE_UNAVAILABLE,
            message="VirtualCourt integration is not configured.",
            retryable=False,
        )

    if provided_key is None or not secrets.compare_digest(provided_key, expected_key):
        raise IntegrationAPIError(
            status_code=401,
            code=IntegrationErrorCode.AUTHENTICATION_FAILED,
            message="Invalid integration credentials.",
            retryable=False,
        )

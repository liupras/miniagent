#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: API-key authentication for VirtualCourt integration endpoints.

from __future__ import annotations

from typing import Annotated

from fastapi import Security
from fastapi.security import APIKeyHeader

from app.core.config import settings
from app.services.integration_auth import authenticate_integration_api_key


INTEGRATION_KEY_HEADER = "X-Integration-Key"
integration_key_header = APIKeyHeader(
    name=INTEGRATION_KEY_HEADER,
    auto_error=False,
    description="Static API key configured for the VirtualCourt integration.",
)


def require_virtual_court_api_key(
    provided_key: Annotated[str | None, Security(integration_key_header)],
) -> None:
    authenticate_integration_api_key(
        provided_key=provided_key,
        expected_key=settings.virtual_court_api_key.get_secret_value(),
    )

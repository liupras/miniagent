#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: Authentication rules for system-to-system integrations.

from __future__ import annotations

import secrets

from app.schemas.exceptions import BaseDomainError


class IntegrationAccessError(BaseDomainError):
    """Base class for failures while authenticating an integration caller."""


class IntegrationNotConfiguredError(IntegrationAccessError):
    error_key = "integration.not_configured"

    def __init__(self) -> None:
        super().__init__(message="Integration API key is not configured")


class InvalidIntegrationCredentialsError(IntegrationAccessError):
    error_key = "integration.authentication_failed"

    def __init__(self) -> None:
        super().__init__(message="Invalid integration credentials")


def authenticate_integration_api_key(
    *,
    provided_key: str | None,
    expected_key: str,
) -> None:
    """Validate a fixed integration API key using constant-time comparison."""
    if not expected_key:
        raise IntegrationNotConfiguredError()

    if provided_key is None or not secrets.compare_digest(
        provided_key,
        expected_key,
    ):
        raise InvalidIntegrationCredentialsError()

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
        super().__init__(message="Internal service token is not configured")


class InvalidIntegrationCredentialsError(IntegrationAccessError):
    error_key = "integration.authentication_failed"

    def __init__(self) -> None:
        super().__init__(message="Invalid integration credentials")


def authenticate_internal_service_token(
    *,
    provided_token: str | None,
    expected_token: str,
) -> None:
    """Validate the shared internal service token in constant time."""
    if not expected_token:
        raise IntegrationNotConfiguredError()

    if provided_token is None or not secrets.compare_digest(
        provided_token,
        expected_token,
    ):
        raise InvalidIntegrationCredentialsError()

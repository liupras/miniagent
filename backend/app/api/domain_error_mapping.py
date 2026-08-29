#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: HTTP mapping for application/domain exceptions.

from app.schemas.exceptions import (
    AlreadyExistsError,
    BaseDomainError,
    InfrastructureError,
    NotFoundError,
    PermissionDeniedError,
    UnsupportedMediaTypeError,
)
from app.services.integration_auth import (
    IntegrationAccessError,
    IntegrationNotConfiguredError,
    InvalidIntegrationCredentialsError,
)
from app.services.virtual_court import (
    JudgeConfigurationError,
    JudgeInvalidResponseError,
    JudgeServiceError,
    JudgeTimeoutError,
    JudgeUnavailableError,
)


# Keep subclasses before their parents: the first matching type wins.
_HTTP_STATUS_BY_ERROR_TYPE: tuple[tuple[type[BaseDomainError], int], ...] = (
    (InvalidIntegrationCredentialsError, 401),
    (IntegrationNotConfiguredError, 503),
    (IntegrationAccessError, 500),
    (JudgeTimeoutError, 504),
    (JudgeInvalidResponseError, 502),
    (JudgeConfigurationError, 503),
    (JudgeUnavailableError, 503),
    (JudgeServiceError, 500),
    (NotFoundError, 404),
    (AlreadyExistsError, 409),
    (UnsupportedMediaTypeError, 415),
    (PermissionDeniedError, 403),
    (InfrastructureError, 503),
    (BaseDomainError, 400),
)


def domain_error_http_status(error: BaseDomainError) -> int:
    """Return the API status for a stable application exception."""
    for error_type, status_code in _HTTP_STATUS_BY_ERROR_TYPE:
        if isinstance(error, error_type):
            return status_code
    return 500

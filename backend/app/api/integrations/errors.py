#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: Error responses shared by system-to-system integration APIs.

from __future__ import annotations
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.domain_error_mapping import domain_error_http_status
from app.core.i18n.error_translation import translate_domain_error
from app.core.logger_config import get_logger
from app.schemas.integrations.virtual_court import (
    IntegrationError,
    IntegrationErrorCode,
    IntegrationErrorResponse,
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


logger = get_logger(__name__)
INTEGRATION_PATH_PREFIX = "/api/v1/integrations/"


def integration_error_response(
    *,
    status_code: int,
    code: IntegrationErrorCode,
    message: str,
    retryable: bool,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    payload = IntegrationErrorResponse(
        error=IntegrationError(
            code=code,
            message=message,
            retryable=retryable,
            details=details or {},
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
    )


async def integration_access_error_handler(
    _request: Request,
    exc: IntegrationAccessError,
) -> JSONResponse:
    if isinstance(exc, IntegrationNotConfiguredError):
        code = IntegrationErrorCode.SERVICE_UNAVAILABLE
    elif isinstance(exc, InvalidIntegrationCredentialsError):
        code = IntegrationErrorCode.AUTHENTICATION_FAILED
    else:
        code = IntegrationErrorCode.INTERNAL_ERROR

    return integration_error_response(
        status_code=domain_error_http_status(exc),
        code=code,
        message=translate_domain_error(exc),
        retryable=False,
    )


async def judge_service_error_handler(
    _request: Request,
    exc: JudgeServiceError,
) -> JSONResponse:
    if isinstance(exc, JudgeConfigurationError):
        code = IntegrationErrorCode.SERVICE_UNAVAILABLE
        retryable = False
    elif isinstance(exc, JudgeUnavailableError):
        code = IntegrationErrorCode.SERVICE_UNAVAILABLE
        retryable = True
    elif isinstance(exc, JudgeTimeoutError):
        code = IntegrationErrorCode.UPSTREAM_TIMEOUT
        retryable = True
    elif isinstance(exc, JudgeInvalidResponseError):
        code = IntegrationErrorCode.MODEL_RESPONSE_INVALID
        retryable = True
    else:
        code = IntegrationErrorCode.INTERNAL_ERROR
        retryable = False

    logger.warning("[VirtualCourt] {}: {}", type(exc).__name__, exc)
    return integration_error_response(
        status_code=domain_error_http_status(exc),
        code=code,
        message=translate_domain_error(exc),
        retryable=retryable,
    )


async def integration_request_validation_handler(
    request: Request,
    exc: RequestValidationError,
):
    if not request.url.path.startswith(INTEGRATION_PATH_PREFIX):
        return await request_validation_exception_handler(request, exc)

    return integration_error_response(
        status_code=422,
        code=IntegrationErrorCode.INVALID_REQUEST,
        message="Request body does not match the integration contract.",
        retryable=False,
    )


def register_integration_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        IntegrationAccessError,
        integration_access_error_handler,
    )
    app.add_exception_handler(JudgeServiceError, judge_service_error_handler)
    app.add_exception_handler(
        RequestValidationError,
        integration_request_validation_handler,
    )

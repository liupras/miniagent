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

from app.core.logger_config import get_logger
from app.schemas.integrations.virtual_court import (
    IntegrationError,
    IntegrationErrorCode,
    IntegrationErrorResponse,
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


class IntegrationAPIError(Exception):
    """A safe, externally versioned integration failure."""

    def __init__(
        self,
        *,
        status_code: int,
        code: IntegrationErrorCode,
        message: str,
        retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = IntegrationErrorResponse(
            error=IntegrationError(
                code=code,
                message=message,
                retryable=retryable,
                details=details or {},
            )
        )


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


async def integration_api_error_handler(
    _request: Request,
    exc: IntegrationAPIError,
) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.payload.model_dump(mode="json"))


async def judge_service_error_handler(
    _request: Request,
    exc: JudgeServiceError,
) -> JSONResponse:
    if isinstance(exc, JudgeConfigurationError):
        status_code = 503
        code = IntegrationErrorCode.SERVICE_UNAVAILABLE
        message = "Judge service is not configured correctly."
        retryable = False
    elif isinstance(exc, JudgeUnavailableError):
        status_code = 503
        code = IntegrationErrorCode.SERVICE_UNAVAILABLE
        message = "Judge service is temporarily unavailable."
        retryable = True
    elif isinstance(exc, JudgeTimeoutError):
        status_code = 504
        code = IntegrationErrorCode.UPSTREAM_TIMEOUT
        message = "Judge decision timed out."
        retryable = True
    elif isinstance(exc, JudgeInvalidResponseError):
        status_code = 502
        code = IntegrationErrorCode.MODEL_RESPONSE_INVALID
        message = "Judge agent returned an invalid response."
        retryable = True
    else:
        status_code = 500
        code = IntegrationErrorCode.INTERNAL_ERROR
        message = "Judge service failed unexpectedly."
        retryable = False

    logger.warning("[VirtualCourt] {}: {}", type(exc).__name__, exc)
    return integration_error_response(
        status_code=status_code,
        code=code,
        message=message,
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
    app.add_exception_handler(IntegrationAPIError, integration_api_error_handler)
    app.add_exception_handler(JudgeServiceError, judge_service_error_handler)
    app.add_exception_handler(
        RequestValidationError,
        integration_request_validation_handler,
    )

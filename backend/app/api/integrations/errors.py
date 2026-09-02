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


def _request_log_context(request: Request) -> tuple[str, str, str, str]:
    """Return non-sensitive request metadata suitable for diagnostic logs."""
    request_id = getattr(request.state, "request_id", "-")
    client = request.client.host if request.client else "-"
    return request.method, request.url.path, client, request_id


def _safe_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Keep validation diagnostics while excluding submitted field values."""
    return [
        {
            "location": list(error.get("loc", ())),
            "message": error.get("msg", "Invalid value"),
            "type": error.get("type", "validation_error"),
        }
        for error in exc.errors()
    ]


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
    request: Request,
    exc: IntegrationAccessError,
) -> JSONResponse:
    if isinstance(exc, IntegrationNotConfiguredError):
        code = IntegrationErrorCode.SERVICE_UNAVAILABLE
    elif isinstance(exc, InvalidIntegrationCredentialsError):
        code = IntegrationErrorCode.AUTHENTICATION_FAILED
    else:
        code = IntegrationErrorCode.INTERNAL_ERROR

    method, path, client, request_id = _request_log_context(request)
    logger.warning(
        "[VirtualCourt] integration request rejected: method={}, path={}, "
        "status={}, error_code={}, client={}, request_id={}",
        method,
        path,
        domain_error_http_status(exc),
        code,
        client,
        request_id,
    )

    return integration_error_response(
        status_code=domain_error_http_status(exc),
        code=code,
        message=translate_domain_error(exc),
        retryable=False,
    )


async def judge_service_error_handler(
    request: Request,
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

    method, path, client, request_id = _request_log_context(request)
    logger.warning(
        "[VirtualCourt] judge request failed: method={}, path={}, status={}, "
        "error_code={}, exception={}, diagnostic_params={}, cause_type={}, "
        "client={}, request_id={}",
        method,
        path,
        domain_error_http_status(exc),
        code,
        type(exc).__name__,
        exc.params,
        type(exc.cause).__name__ if exc.cause is not None else "-",
        client,
        request_id,
    )
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

    method, path, client, request_id = _request_log_context(request)
    logger.warning(
        "[VirtualCourt] request validation failed: method={}, path={}, "
        "status=422, error_code={}, client={}, request_id={}, errors={}",
        method,
        path,
        IntegrationErrorCode.INVALID_REQUEST,
        client,
        request_id,
        _safe_validation_errors(exc),
    )

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

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: Global FastAPI exception-to-HTTP response mapping.

from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.integrations.errors import (
    INTEGRATION_PATH_PREFIX,
    integration_error_response,
)
from app.core.i18n.i18n import t
from app.core.logger_config import get_logger
from app.schemas.common import ApiResponse
from app.schemas.exceptions import (
    AlreadyExistsError,
    BaseDomainError,
    InfrastructureError,
    NotFoundError,
    PermissionDeniedError,
    UnsupportedMediaTypeError,
)
from app.schemas.integrations.virtual_court import IntegrationErrorCode


logger = get_logger(__name__)


def create_api_response(
    *,
    status_code: int,
    code: int,
    message: str,
    data: Any = None,
) -> JSONResponse:
    """Build the standard MiniAgent HTTP response envelope."""
    payload = ApiResponse(code=code, message=message, data=data)
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(exclude_none=True),
    )


def _add_request_headers(request: Request, response: JSONResponse) -> None:
    """Preserve correlation headers when an exception escapes middleware."""
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        response.headers["X-Request-ID"] = request_id

    started_at = getattr(request.state, "request_started_at", None)
    if started_at is not None:
        response.headers["X-Process-Time"] = str(time.time() - started_at)


async def domain_error_handler(
    request: Request,
    exc: BaseDomainError,
) -> JSONResponse:
    """Translate stable application errors into the standard API envelope."""
    if request.url.path.startswith(INTEGRATION_PATH_PREFIX):
        logger.warning(
            "Unhandled integration domain error {}: {}",
            type(exc).__name__,
            exc,
        )
        return integration_error_response(
            status_code=500,
            code=IntegrationErrorCode.INTERNAL_ERROR,
            message=t("integration.unexpected_error"),
            retryable=False,
        )

    if isinstance(exc, NotFoundError):
        status_code = 404
    elif isinstance(exc, AlreadyExistsError):
        status_code = 409
    elif isinstance(exc, UnsupportedMediaTypeError):
        status_code = 415
    elif isinstance(exc, PermissionDeniedError):
        status_code = 403
    elif isinstance(exc, InfrastructureError):
        status_code = 503
    else:
        status_code = 400

    logger.warning("{}: {}", type(exc).__name__, exc)
    return create_api_response(
        status_code=status_code,
        code=status_code,
        message=exc.to_detail(),
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Return a safe response for unexpected failures and log diagnostics."""
    logger.exception("Unhandled exception: {}", exc)

    if request.url.path.startswith(INTEGRATION_PATH_PREFIX):
        response = integration_error_response(
            status_code=500,
            code=IntegrationErrorCode.INTERNAL_ERROR,
            message=t("integration.unexpected_error"),
            retryable=False,
        )
    else:
        detail = t("common.error_500")
        response = create_api_response(
            status_code=500,
            code=500,
            message=t("common.error_500"),
            data={"error": detail},
        )

    _add_request_headers(request, response)
    return response


def register_global_exception_handlers(app: FastAPI) -> None:
    """Register application-wide exception handlers on a FastAPI app."""
    app.add_exception_handler(BaseDomainError, domain_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

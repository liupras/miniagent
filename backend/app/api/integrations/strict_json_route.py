#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-09-17
# @description: Reusable bounded, duplicate-safe JSON route for integration APIs.

from fastapi import Request
from fastapi.routing import APIRoute

from app.api.integrations.errors import integration_error_response
from app.schemas.integrations.strict_json import strict_json
from app.schemas.integrations.virtual_court import IntegrationErrorCode


REQUEST_MAX_BYTES = 524288


class StrictIntegrationRoute(APIRoute):
    """Validate the raw JSON body before FastAPI performs model binding."""

    request_max_bytes = REQUEST_MAX_BYTES

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            chunks = bytearray()
            try:
                async for chunk in request.stream():
                    if len(chunks) + len(chunk) > self.request_max_bytes:
                        return integration_error_response(
                            status_code=422,
                            code=IntegrationErrorCode.INVALID_REQUEST,
                            message="请求超过大小限制。",
                            retryable=False,
                            details={"reason": "body_size"},
                        )
                    chunks.extend(chunk)
                strict_json(bytes(chunks))
            except (ValueError, UnicodeError, RecursionError):
                return integration_error_response(
                    status_code=422,
                    code=IntegrationErrorCode.INVALID_REQUEST,
                    message="请求必须是合法且没有重复字段的 UTF-8 JSON。",
                    retryable=False,
                    details={"reason": "invalid_json"},
                )

            request._body = bytes(chunks)
            return await original(request)

        return handler

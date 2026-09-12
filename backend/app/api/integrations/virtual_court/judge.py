"""Split JudgeAPI V2 routes with bounded, duplicate-safe JSON bodies."""

from time import perf_counter

from fastapi import APIRouter, Depends, Request, Security
from fastapi.routing import APIRoute

from app.api.integrations.auth import require_virtual_court_api_key
from app.api.integrations.errors import integration_error_response
from app.core.logger_config import get_logger
from app.schemas.integrations.virtual_court import (
    IntegrationErrorCode,
    IntegrationErrorResponse,
    JudgeLawCheckRequestV2,
    JudgeLawCheckResponseV2,
    JudgeNextActionRequestV2,
    JudgeNextActionResponseV2,
)
from app.schemas.integrations.virtual_court.judge import (
    REQUEST_MAX_BYTES,
    strict_json,
)
from app.services.virtual_court import LawCheckService, NextActionService


logger = get_logger(__name__)
ERROR_RESPONSES = {
    code: {'model': IntegrationErrorResponse}
    for code in (401, 422, 429, 500, 502, 503, 504)
}


class JudgeRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            chunks = bytearray()
            try:
                async for chunk in request.stream():
                    if len(chunks) + len(chunk) > REQUEST_MAX_BYTES:
                        return integration_error_response(
                            status_code=422,
                            code=IntegrationErrorCode.INVALID_REQUEST,
                            message='请求超过大小限制。',
                            retryable=False,
                            details={'reason': 'body_size'},
                        )
                    chunks.extend(chunk)
                strict_json(bytes(chunks))
            except (ValueError, UnicodeError, RecursionError):
                return integration_error_response(
                    status_code=422,
                    code=IntegrationErrorCode.INVALID_REQUEST,
                    message='请求必须是合法且没有重复字段的 UTF-8 JSON。',
                    retryable=False,
                    details={'reason': 'invalid_json'},
                )
            request._body = bytes(chunks)
            return await original(request)

        return handler


router = APIRouter(route_class=JudgeRoute)


def get_law_check_service(request: Request):
    return request.app.state.container.law_check_service


def get_next_action_service(request: Request):
    return request.app.state.container.next_action_service


@router.post(
    '/judge/law-check',
    response_model=JudgeLawCheckResponseV2,
    responses=ERROR_RESPONSES,
    summary='Check one committed party speech for a legal question',
)
async def law_check(
    body: JudgeLawCheckRequestV2,
    _authenticated: None = Security(require_virtual_court_api_key),
    service: LawCheckService = Depends(get_law_check_service),
) -> JudgeLawCheckResponseV2:
    started = perf_counter()
    logger.info(
        '[LawCheckV2] accepted: state_version={}, role={}, text_codepoints={}, context_codepoints={}',
        body.state_version,
        body.role,
        len(body.text),
        len(body.context),
    )
    response = await service.check(body)
    logger.info(
        '[LawCheckV2] completed: state_version={}, decision={}, elapsed_ms={:.1f}',
        response.state_version,
        response.decision,
        (perf_counter() - started) * 1000,
    )
    return response


@router.post(
    '/judge/next-action',
    response_model=JudgeNextActionResponseV2,
    responses=ERROR_RESPONSES,
    summary='Choose one constrained investigation or debate action',
)
async def next_action(
    body: JudgeNextActionRequestV2,
    _authenticated: None = Security(require_virtual_court_api_key),
    service: NextActionService = Depends(get_next_action_service),
) -> JudgeNextActionResponseV2:
    started = perf_counter()
    logger.info(
        '[NextActionV2] accepted: phase={}, state_version={}, actions={}, targets={}, records={}',
        body.phase,
        body.state_version,
        len(body.allowed_actions),
        len(body.allowed_targets),
        len(body.records),
    )
    response = await service.decide(body)
    logger.info(
        '[NextActionV2] completed: phase={}, state_version={}, decision={}, elapsed_ms={:.1f}',
        body.phase,
        response.state_version,
        response.decision,
        (perf_counter() - started) * 1000,
    )
    return response

"""Party Reply API V1 route."""

from time import perf_counter

from fastapi import APIRouter, Depends, Request, Security

from app.api.integrations.auth import require_internal_service_token
from app.api.integrations.strict_json_route import StrictIntegrationRoute
from app.core.logger_config import get_logger
from app.schemas.integrations.virtual_court import (
    IntegrationErrorResponse,
    PartyReplyRequestV1,
    PartyReplyResponseV1,
)
from app.services.virtual_court import PartyReplyService


logger = get_logger(__name__)
ERROR_RESPONSES = {
    code: {"model": IntegrationErrorResponse}
    for code in (401, 422, 429, 500, 502, 503, 504)
}

router = APIRouter(route_class=StrictIntegrationRoute)


def get_party_reply_service(request: Request):
    return request.app.state.container.party_reply_service


@router.post(
    "/party/reply",
    response_model=PartyReplyResponseV1,
    responses=ERROR_RESPONSES,
    summary="Generate one party answer to one courtroom inquiry question",
)
async def party_reply(
    body: PartyReplyRequestV1,
    _authenticated: None = Security(require_internal_service_token),
    service: PartyReplyService = Depends(get_party_reply_service),
) -> PartyReplyResponseV1:
    started = perf_counter()
    logger.info(
        "[PartyReplyV1] accepted: state_version={}, role={}, question_codepoints={}, records={}",
        body.state_version,
        body.role,
        len(body.question),
        len(body.records),
    )
    response = await service.reply(body)
    logger.info(
        "[PartyReplyV1] completed: state_version={}, role={}, speech_codepoints={}, elapsed_ms={:.1f}",
        response.state_version,
        body.role,
        len(response.speech),
        (perf_counter() - started) * 1000,
    )
    return response

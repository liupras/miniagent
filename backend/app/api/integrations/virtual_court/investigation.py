"""Dedicated V3 endpoints for the unified investigation agents."""

from time import perf_counter

from fastapi import APIRouter, Depends, Request, Security

from app.api.integrations.auth import require_internal_service_token
from app.api.integrations.strict_json_route import StrictIntegrationRoute
from app.core.logger_config import get_logger
from app.schemas.integrations.virtual_court import IntegrationErrorResponse
from app.schemas.integrations.virtual_court.investigation import (
    JudgeNextActionRequest,
    JudgeNextActionResponse,
    ParticipantIntentRequest,
    ParticipantIntentResponse,
    ParticipantSpeechRequest,
    ParticipantSpeechResponse,
)
from app.services.virtual_court.investigation_service import InvestigationAgentService


logger = get_logger(__name__)
router = APIRouter(route_class=StrictIntegrationRoute)
ERROR_RESPONSES = {
    code: {"model": IntegrationErrorResponse}
    for code in (401, 422, 429, 500, 502, 503, 504)
}


def get_investigation_service(request: Request):
    return request.app.state.container.investigation_agent_service


@router.post(
    "/investigation/participant/intent",
    response_model=ParticipantIntentResponse,
    response_model_exclude_unset=True,
    responses=ERROR_RESPONSES,
    summary="Decide whether one party requests the floor",
)
async def participant_intent(
    body: ParticipantIntentRequest,
    _authenticated: None = Security(require_internal_service_token),
    service: InvestigationAgentService = Depends(get_investigation_service),
) -> ParticipantIntentResponse:
    started = perf_counter()
    result = await service.intent(body)
    logger.info("[InvestigationV3] intent: decision={}, records={}, elapsed_ms={:.1f}",
                result.decision, len(body.records), (perf_counter() - started) * 1000)
    return result


@router.post(
    "/investigation/participant/speech",
    response_model=ParticipantSpeechResponse,
    responses=ERROR_RESPONSES,
    summary="Generate speech for an authorized party turn",
)
async def participant_speech(
    body: ParticipantSpeechRequest,
    _authenticated: None = Security(require_internal_service_token),
    service: InvestigationAgentService = Depends(get_investigation_service),
) -> ParticipantSpeechResponse:
    started = perf_counter()
    result = await service.speech(body)
    logger.info("[InvestigationV3] speech: records={}, speech_codepoints={}, elapsed_ms={:.1f}",
                len(body.records), len(result.speech), (perf_counter() - started) * 1000)
    return result


@router.post(
    "/investigation/judge/next-action",
    response_model=JudgeNextActionResponse,
    response_model_exclude_unset=True,
    responses=ERROR_RESPONSES,
    summary="Choose one constrained investigation judge action",
)
async def judge_next_action(
    body: JudgeNextActionRequest,
    _authenticated: None = Security(require_internal_service_token),
    service: InvestigationAgentService = Depends(get_investigation_service),
) -> JudgeNextActionResponse:
    started = perf_counter()
    result = await service.next_action(body)
    logger.info("[InvestigationV3] judge: decision={}, records={}, elapsed_ms={:.1f}",
                result.decision, len(body.records), (perf_counter() - started) * 1000)
    return result

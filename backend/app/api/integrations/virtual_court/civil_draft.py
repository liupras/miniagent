"""VirtualCourt civil case draft generation V2 route."""

from time import perf_counter

from fastapi import APIRouter, Depends, Request, Security

from app.api.integrations.auth import require_internal_service_token
from app.api.integrations.strict_json_route import StrictIntegrationRoute
from app.core.logger_config import get_logger
from app.schemas.integrations.virtual_court import (
    CivilCaseDraftGenerateRequestV2,
    CivilCaseDraftGenerateResponseV2,
    IntegrationErrorResponse,
)
from app.services.virtual_court import CivilDraftService


logger = get_logger(__name__)
router = APIRouter(route_class=StrictIntegrationRoute)
ERROR_RESPONSES = {
    code: {"model": IntegrationErrorResponse}
    for code in (401, 422, 429, 500, 502, 503, 504)
}


def get_civil_draft_service(request: Request):
    return request.app.state.container.civil_draft_service


@router.post(
    "/cases/civil/draft/generate",
    response_model=CivilCaseDraftGenerateResponseV2,
    responses=ERROR_RESPONSES,
    summary="Generate a reviewable civil case draft from source materials",
)
async def generate_civil_draft(
    body: CivilCaseDraftGenerateRequestV2,
    _authenticated: None = Security(require_internal_service_token),
    service: CivilDraftService = Depends(get_civil_draft_service),
) -> CivilCaseDraftGenerateResponseV2:
    started = perf_counter()
    source_codepoints = sum(len(item.text) for item in body.documents)
    logger.info(
        "[CivilDraftV2] accepted: documents={}, source_codepoints={}",
        len(body.documents),
        source_codepoints,
    )
    response = await service.generate(body)
    logger.info(
        "[CivilDraftV2] completed: claims={}, evidence_groups={}, issues={}, elapsed_ms={:.1f}",
        len(response.draft.claims),
        len(response.draft.evidenceGroups),
        len(response.issues),
        (perf_counter() - started) * 1000,
    )
    return response

"""Case-type-neutral draft generation API."""

from time import perf_counter

from fastapi import APIRouter, Depends, Request, Security

from app.api.integrations.auth import require_internal_service_token
from app.api.integrations.strict_json_route import StrictIntegrationRoute
from app.core.logger_config import get_logger
from app.schemas.integrations.virtual_court import (
    CaseDraftGenerateRequestV1,
    CaseDraftGenerateResponseV1,
    IntegrationErrorResponse,
)
from app.schemas.integrations.virtual_court.case_draft import REQUEST_MAX_BYTES
from app.services.virtual_court import CaseDraftService


logger = get_logger(__name__)


class CaseDraftIntegrationRoute(StrictIntegrationRoute):
    request_max_bytes = REQUEST_MAX_BYTES


router = APIRouter(route_class=CaseDraftIntegrationRoute)
ERROR_RESPONSES = {
    code: {"model": IntegrationErrorResponse}
    for code in (401, 422, 429, 500, 502, 503, 504)
}


def get_case_draft_service(request: Request):
    return request.app.state.container.case_draft_service


@router.post(
    "/case-drafts/generate",
    response_model=CaseDraftGenerateResponseV1,
    responses=ERROR_RESPONSES,
    summary="Generate a reviewable case draft under a supplied JSON contract",
)
async def generate_case_draft(
    body: CaseDraftGenerateRequestV1,
    _authenticated: None = Security(require_internal_service_token),
    service: CaseDraftService = Depends(get_case_draft_service),
) -> CaseDraftGenerateResponseV1:
    started = perf_counter()
    logger.info(
        "[CaseDraftV1] accepted: contract={}, documents={}, source_codepoints={}",
        body.draftContract.contractId,
        len(body.documents),
        sum(len(item.text) for item in body.documents),
    )
    response = await service.generate(body)
    logger.info(
        "[CaseDraftV1] completed: contract={}, issues={}, elapsed_ms={:.1f}",
        body.draftContract.contractId,
        len(response.issues),
        (perf_counter() - started) * 1000,
    )
    return response

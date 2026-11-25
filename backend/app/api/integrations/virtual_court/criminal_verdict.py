"""Authenticated endpoint for one criminal training verdict."""

from fastapi import APIRouter, Depends, Request, Security

from app.api.integrations.auth import require_internal_service_token
from app.api.integrations.strict_json_route import StrictIntegrationRoute
from app.schemas.integrations.virtual_court import IntegrationErrorResponse
from app.schemas.integrations.virtual_court.criminal_verdict import (
    CriminalVerdictRequest, CriminalVerdictResponse,
)
from app.services.virtual_court.criminal_verdict_service import CriminalVerdictService


router = APIRouter(route_class=StrictIntegrationRoute)
ERROR_RESPONSES = {code: {"model": IntegrationErrorResponse}
                   for code in (401, 422, 429, 500, 502, 503, 504)}


def get_service(request: Request) -> CriminalVerdictService:
    return request.app.state.container.criminal_verdict_service


@router.post(
    "/criminal/verdict",
    response_model=CriminalVerdictResponse,
    response_model_exclude_none=True,
    responses=ERROR_RESPONSES,
    summary="Generate a criminal training verdict from a frozen basis",
)
async def criminal_verdict(
    body: CriminalVerdictRequest,
    _authenticated: None = Security(require_internal_service_token),
    service: CriminalVerdictService = Depends(get_service),
) -> CriminalVerdictResponse:
    return await service.run(body)

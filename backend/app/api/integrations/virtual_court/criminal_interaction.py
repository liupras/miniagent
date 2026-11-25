"""Authenticated MiniAgent endpoint for criminal courtroom interactions."""

from fastapi import APIRouter, Depends, Request, Security

from app.api.integrations.auth import require_internal_service_token
from app.api.integrations.strict_json_route import StrictIntegrationRoute
from app.schemas.integrations.virtual_court import IntegrationErrorResponse
from app.schemas.integrations.virtual_court.criminal_interaction import (
    CriminalInteractionRequest, CriminalInteractionResponse,
)
from app.services.virtual_court.criminal_interaction_service import CriminalInteractionService


router = APIRouter(route_class=StrictIntegrationRoute)
ERROR_RESPONSES = {
    code: {"model": IntegrationErrorResponse}
    for code in (401, 422, 429, 500, 502, 503, 504)
}


def get_service(request: Request) -> CriminalInteractionService:
    return request.app.state.container.criminal_interaction_service


@router.post(
    "/criminal/interaction",
    response_model=CriminalInteractionResponse,
    response_model_exclude_none=True,
    responses=ERROR_RESPONSES,
    summary="Run one authorized criminal courtroom interaction",
)
async def criminal_interaction(
    body: CriminalInteractionRequest,
    _authenticated: None = Security(require_internal_service_token),
    service: CriminalInteractionService = Depends(get_service),
) -> CriminalInteractionResponse:
    return await service.run(body)

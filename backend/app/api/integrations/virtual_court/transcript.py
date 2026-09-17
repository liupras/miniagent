#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-09-17
# @description:TranscriptAPI V2 route for stateless court-record generation.

from time import perf_counter

from fastapi import APIRouter, Depends, Request, Security

from app.api.integrations.auth import require_virtual_court_api_key
from app.api.integrations.strict_json_route import StrictIntegrationRoute
from app.core.logger_config import get_logger
from app.schemas.integrations.virtual_court import (
    IntegrationErrorResponse,
    TranscriptGenerateRequestV2,
    TranscriptGenerateResponseV2,
)
from app.schemas.integrations.virtual_court.judge import content_size
from app.services.virtual_court import TranscriptService


logger = get_logger(__name__)
ERROR_RESPONSES = {
    code: {"model": IntegrationErrorResponse}
    for code in (401, 422, 429, 500, 502, 503, 504)
}

router = APIRouter(route_class=StrictIntegrationRoute)


def get_transcript_service(request: Request):
    return request.app.state.container.transcript_service


@router.post(
    "/transcript/generate",
    response_model=TranscriptGenerateResponseV2,
    responses=ERROR_RESPONSES,
    summary="Generate a transcript draft from complete court material",
)
async def generate_transcript(
    body: TranscriptGenerateRequestV2,
    _authenticated: None = Security(require_virtual_court_api_key),
    service: TranscriptService = Depends(get_transcript_service),
) -> TranscriptGenerateResponseV2:
    started = perf_counter()
    material_codepoints = content_size(body.case_context.model_dump())
    material_codepoints += sum(
        content_size(record.model_dump()) for record in body.records
    )
    logger.info(
        "[TranscriptV2] accepted: state_version={}, records={}, material_codepoints={}",
        body.state_version,
        len(body.records),
        material_codepoints,
    )
    response = await service.generate(body)
    logger.info(
        "[TranscriptV2] completed: state_version={}, transcript_codepoints={}, elapsed_ms={:.1f}",
        response.state_version,
        len(response.transcript),
        (perf_counter() - started) * 1000,
    )
    return response

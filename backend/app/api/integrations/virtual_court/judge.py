#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-09-17
# @description: Split JudgeAPI V2 routes with bounded, duplicate-safe JSON bodies.

from time import perf_counter

from fastapi import APIRouter, Depends, Request, Security

from app.api.integrations.auth import require_virtual_court_api_key
from app.api.integrations.strict_json_route import StrictIntegrationRoute
from app.core.logger_config import get_logger
from app.schemas.integrations.virtual_court import (
    IntegrationErrorResponse,
    JudgeLawCheckRequestV2,
    JudgeLawCheckResponseV2,
    JudgeNextActionRequestV2,
    JudgeNextActionResponseV2,
)
from app.services.virtual_court import LawCheckService, NextActionService


logger = get_logger(__name__)
ERROR_RESPONSES = {
    code: {'model': IntegrationErrorResponse}
    for code in (401, 422, 429, 500, 502, 503, 504)
}


router = APIRouter(route_class=StrictIntegrationRoute)


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
    summary='Choose one constrained investigation action',
)
async def next_action(
    body: JudgeNextActionRequestV2,
    _authenticated: None = Security(require_virtual_court_api_key),
    service: NextActionService = Depends(get_next_action_service),
) -> JudgeNextActionResponseV2:
    started = perf_counter()
    logger.info(
        '[NextActionV2] accepted: state_version={}, actions={}, targets={}, records={}',
        body.state_version,
        len(body.allowed_actions),
        len(body.allowed_targets),
        len(body.records),
    )
    response = await service.decide(body)
    logger.info(
        '[NextActionV2] completed: state_version={}, decision={}, elapsed_ms={:.1f}',
        response.state_version,
        response.decision,
        (perf_counter() - started) * 1000,
    )
    return response

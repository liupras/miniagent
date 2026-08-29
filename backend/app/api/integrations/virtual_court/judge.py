#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: HTTP endpoint for VirtualCourt sole-judge decisions.

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Security, status

from app.api.integrations.auth import require_virtual_court_api_key
from app.schemas.integrations.virtual_court import (
    IntegrationErrorResponse,
    JudgeDecisionRequest,
    JudgeDecisionResponse,
)
from app.services.virtual_court import JudgeService


router = APIRouter()


def get_judge_service(request: Request) -> JudgeService:
    return request.app.state.container.judge_service


ERROR_RESPONSES = {
    401: {"model": IntegrationErrorResponse},
    422: {"model": IntegrationErrorResponse},
    500: {"model": IntegrationErrorResponse},
    502: {"model": IntegrationErrorResponse},
    503: {"model": IntegrationErrorResponse},
    504: {"model": IntegrationErrorResponse},
}


@router.post(
    "/judge/decide",
    response_model=JudgeDecisionResponse,
    status_code=status.HTTP_200_OK,
    responses=ERROR_RESPONSES,
    summary="Request one constrained sole-judge decision",
)
async def decide(
    body: JudgeDecisionRequest,
    _authenticated: None = Security(require_virtual_court_api_key),
    service: JudgeService = Depends(get_judge_service),
) -> JudgeDecisionResponse:
    return await service.decide(body)

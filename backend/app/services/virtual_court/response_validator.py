#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: Strict parsing and request-aware validation for judge agent output.

from __future__ import annotations

from pydantic import ValidationError

from app.schemas.integrations.virtual_court import (
    ActionType,
    JudgeAgentOutput,
    JudgeDecisionRequest,
    JudgeDecisionResponse,
)

from .exceptions import JudgeInvalidResponseError


def validate_judge_agent_output(
    raw_output: str,
    request: JudgeDecisionRequest,
) -> JudgeDecisionResponse:
    """Parse exact JSON, enforce request permissions, and inject state_version.

    The raw model output must be one JSON object matching ``JudgeAgentOutput``.
    Markdown fences, prose, extra fields, missing fields, and type coercion are
    rejected. The model never generates ``state_version``; it is copied from
    the validated request after all output checks pass.
    """

    if not isinstance(raw_output, str) or not raw_output.strip():
        raise JudgeInvalidResponseError("judge output must be a non-empty JSON string")

    try:
        output = JudgeAgentOutput.model_validate_json(raw_output)
    except (ValidationError, ValueError) as exc:
        raise JudgeInvalidResponseError(
            "judge output does not match the strict response schema"
        ) from exc

    action = output.action
    if (
        action.type != ActionType.NO_ACTION
        and action.type not in request.allowed_actions
    ):
        raise JudgeInvalidResponseError(
            f"action {action.type} is not allowed for the current request"
        )

    if (
        action.target_role is not None
        and action.target_role not in request.allowed_targets
    ):
        raise JudgeInvalidResponseError(
            f"target {action.target_role} is not allowed for the current request"
        )

    return JudgeDecisionResponse(
        state_version=request.state_version,
        **output.model_dump(),
    )

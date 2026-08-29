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
        raise JudgeInvalidResponseError(
            params={"reason": "empty_output"},
        )

    try:
        output = JudgeAgentOutput.model_validate_json(raw_output)
    except (ValidationError, ValueError) as exc:
        raise JudgeInvalidResponseError(
            params={"reason": "schema_validation_failed"},
            cause=exc,
        ) from exc

    action = output.action
    if (
        action.type != ActionType.NO_ACTION
        and action.type not in request.allowed_actions
    ):
        raise JudgeInvalidResponseError(
            params={
                "reason": "action_not_allowed",
                "action": action.type.value,
            }
        )

    if (
        action.target_role is not None
        and action.target_role not in request.allowed_targets
    ):
        raise JudgeInvalidResponseError(
            params={
                "reason": "target_not_allowed",
                "target": action.target_role.value,
            }
        )

    return JudgeDecisionResponse(
        state_version=request.state_version,
        **output.model_dump(),
    )

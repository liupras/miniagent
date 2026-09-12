"""Strict JSON and request-bound output validation; no silent repair/coercion."""
from pydantic import ValidationError
from app.schemas.integrations.virtual_court.judge import (
    JudgeAgentOutput,
    JudgeDecisionResponse,
    JudgeLawCheckResponseV2,
    JudgeNextActionResponseV2,
    RESPONSE_MAX_BYTES,
    strict_json,
)
from .exceptions import JudgeInvalidResponseError

def validate_judge_agent_output(raw_output, request):
    try:
        if not isinstance(raw_output, str) or len(raw_output.encode('utf-8')) > RESPONSE_MAX_BYTES:
            raise ValueError('output size')
        output = JudgeAgentOutput.model_validate(strict_json(raw_output))
    except (ValidationError, ValueError, UnicodeError, RecursionError) as exc:
        field = 'response'
        if isinstance(exc, ValidationError):
            # Use schema location only, never echo submitted field values.
            field = '.'.join(str(v) for v in exc.errors()[0]['loc']) or 'response'
        raise JudgeInvalidResponseError(params={'reason':'schema_validation_failed', 'field':field}, cause=exc) from exc
    if output.decision not in request.allowed_decisions:
        raise JudgeInvalidResponseError(params={'reason':'decision_not_allowed','field':'decision'})
    if output.target is not None and output.target not in request.allowed_targets:
        raise JudgeInvalidResponseError(params={'reason':'target_not_allowed','field':'target'})
    response = JudgeDecisionResponse(state_version=request.state_version, **output.model_dump())
    if len(response.model_dump_json().encode('utf-8')) > RESPONSE_MAX_BYTES:
        raise JudgeInvalidResponseError(params={'reason':'response_size','field':'response'})
    return response


def validate_law_check_agent_output(raw_output, request):
    """Validate isolated law-check output and inject the trusted version."""

    try:
        if not isinstance(raw_output, str):
            raise ValueError('output type')
        data = strict_json(raw_output, max_bytes=RESPONSE_MAX_BYTES)
        if not isinstance(data, dict) or 'state_version' in data:
            raise ValueError('agent must not provide state_version')
        response = JudgeLawCheckResponseV2(
            state_version=request.state_version,
            **data,
        )
    except (ValidationError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        field = 'response'
        if isinstance(exc, ValidationError):
            field = '.'.join(str(value) for value in exc.errors()[0]['loc']) or 'response'
        raise JudgeInvalidResponseError(
            params={'reason': 'schema_validation_failed', 'field': field},
            cause=exc,
        ) from exc
    if len(response.model_dump_json().encode('utf-8')) > RESPONSE_MAX_BYTES:
        raise JudgeInvalidResponseError(
            params={'reason': 'response_size', 'field': 'response'}
        )
    return response


def validate_next_action_agent_output(raw_output, request):
    """Validate a phase decision against the caller's explicit permissions."""

    try:
        if not isinstance(raw_output, str):
            raise ValueError('output type')
        data = strict_json(raw_output, max_bytes=RESPONSE_MAX_BYTES)
        if not isinstance(data, dict) or 'state_version' in data:
            raise ValueError('agent must not provide state_version')
        response = JudgeNextActionResponseV2(
            state_version=request.state_version,
            **data,
        )
    except (ValidationError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        field = 'response'
        if isinstance(exc, ValidationError):
            field = '.'.join(str(value) for value in exc.errors()[0]['loc']) or 'response'
        raise JudgeInvalidResponseError(
            params={'reason': 'schema_validation_failed', 'field': field},
            cause=exc,
        ) from exc
    if response.decision not in request.allowed_actions:
        raise JudgeInvalidResponseError(
            params={'reason': 'decision_not_allowed', 'field': 'decision'}
        )
    if response.target is not None and response.target not in request.allowed_targets:
        raise JudgeInvalidResponseError(
            params={'reason': 'target_not_allowed', 'field': 'target'}
        )
    if len(response.model_dump_json().encode('utf-8')) > RESPONSE_MAX_BYTES:
        raise JudgeInvalidResponseError(
            params={'reason': 'response_size', 'field': 'response'}
        )
    return response

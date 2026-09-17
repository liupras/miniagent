#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: Strict validation for untrusted transcript-agent output.

from pydantic import ValidationError

from app.schemas.integrations.strict_json import strict_json
from app.schemas.integrations.virtual_court import TranscriptGenerateResponseV2
from app.schemas.integrations.virtual_court.transcript import (
    TRANSCRIPT_RESPONSE_MAX_BYTES,
)

from .exceptions import TranscriptInvalidResponseError


def validate_transcript_agent_output(raw_output, request):
    """Validate the agent payload and inject the caller's trusted version."""

    try:
        if not isinstance(raw_output, str):
            raise ValueError("output type")
        data = strict_json(raw_output, max_bytes=TRANSCRIPT_RESPONSE_MAX_BYTES)
        if not isinstance(data, dict) or "state_version" in data:
            raise ValueError("agent must not provide state_version")
        response = TranscriptGenerateResponseV2(
            state_version=request.state_version,
            **data,
        )
    except (ValidationError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        field = "response"
        if isinstance(exc, ValidationError):
            field = ".".join(str(value) for value in exc.errors()[0]["loc"])
            field = field or "response"
        raise TranscriptInvalidResponseError(
            params={"reason": "schema_validation_failed", "field": field},
            cause=exc,
        ) from exc

    if len(response.model_dump_json().encode("utf-8")) > TRANSCRIPT_RESPONSE_MAX_BYTES:
        raise TranscriptInvalidResponseError(
            params={"reason": "response_size", "field": "response"}
        )
    return response

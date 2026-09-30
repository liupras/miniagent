"""Strict validation for untrusted party-responder output."""

from pydantic import ValidationError

from app.schemas.integrations.strict_json import strict_json
from app.schemas.integrations.virtual_court import PartyReplyResponseV1
from app.schemas.integrations.virtual_court.party_reply import (
    PARTY_REPLY_RESPONSE_MAX_BYTES,
)

from .exceptions import PartyReplyInvalidResponseError


def validate_party_reply_agent_output(raw_output, request):
    """Validate agent JSON and inject the caller's trusted state version."""

    try:
        if not isinstance(raw_output, str):
            raise ValueError("output type")
        data = strict_json(raw_output, max_bytes=PARTY_REPLY_RESPONSE_MAX_BYTES)
        if not isinstance(data, dict) or "state_version" in data:
            raise ValueError("agent must not provide state_version")
        response = PartyReplyResponseV1(
            state_version=request.state_version,
            **data,
        )
    except (ValidationError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        field = "response"
        if isinstance(exc, ValidationError):
            field = ".".join(str(value) for value in exc.errors()[0]["loc"])
            field = field or "response"
        raise PartyReplyInvalidResponseError(
            params={"reason": "schema_validation_failed", "field": field},
            cause=exc,
        ) from exc

    if len(response.model_dump_json().encode("utf-8")) > PARTY_REPLY_RESPONSE_MAX_BYTES:
        raise PartyReplyInvalidResponseError(
            params={"reason": "response_size", "field": "response"}
        )
    return response

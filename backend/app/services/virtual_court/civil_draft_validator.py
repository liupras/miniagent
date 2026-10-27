"""Validate generated civil draft JSON against the response contract."""

from pydantic import ValidationError

from app.schemas.integrations.strict_json import strict_json
from app.schemas.integrations.virtual_court import CivilCaseDraftGenerateResponseV1
from app.schemas.integrations.virtual_court.civil_case_draft import CIVIL_DRAFT_RESPONSE_MAX_BYTES

from .exceptions import CivilDraftInvalidResponseError


def validate_civil_draft_agent_output(raw_output):
    """Reject malformed output and unsupported response fields."""
    try:
        if not isinstance(raw_output, str):
            raise ValueError("output type")
        data = strict_json(raw_output, max_bytes=CIVIL_DRAFT_RESPONSE_MAX_BYTES)
        response = CivilCaseDraftGenerateResponseV1.model_validate(data)
    except (ValidationError, TypeError, ValueError, KeyError, IndexError, UnicodeError, RecursionError) as exc:
        field = "response"
        if isinstance(exc, ValidationError):
            field = ".".join(str(part) for part in exc.errors()[0]["loc"]) or field
        raise CivilDraftInvalidResponseError(
            params={"reason": "schema_validation_failed", "field": field},
            cause=exc,
        ) from exc
    return response

"""Validate model output using the caller's draft schema."""

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.schemas.integrations.strict_json import strict_json
from app.schemas.integrations.virtual_court.case_draft import (
    RESPONSE_MAX_BYTES,
    CaseDraftGenerateResponseV1,
)

from .exceptions import CaseDraftInvalidResponseError


def validate_case_draft_agent_output(raw_output, request):
    try:
        data = strict_json(raw_output, max_bytes=RESPONSE_MAX_BYTES)
        response = CaseDraftGenerateResponseV1.model_validate(data)
        errors = Draft202012Validator(request.draftContract.draftSchema).iter_errors(response.draft)
        first = next(errors, None)
        if first is not None:
            path = "/".join(str(part) for part in first.absolute_path)
            raise ValueError(f"draft/{path}: {first.message}"[:800])
        return response
    except (ValidationError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        field = "response"
        if isinstance(exc, ValidationError):
            field = ".".join(str(part) for part in exc.errors()[0]["loc"]) or field
        elif isinstance(exc, ValueError):
            field = str(exc)[:800]
        raise CaseDraftInvalidResponseError(
            params={"reason": "schema_validation_failed", "field": field}, cause=exc,
        ) from exc

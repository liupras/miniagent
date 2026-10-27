"""Validate a generated civil draft against its untrusted source documents."""

import re

from pydantic import ValidationError

from app.schemas.integrations.strict_json import strict_json
from app.schemas.integrations.virtual_court import CivilCaseDraftGenerateResponseV1
from app.schemas.integrations.virtual_court.civil_case_draft import CIVIL_DRAFT_RESPONSE_MAX_BYTES

from .exceptions import CivilDraftInvalidResponseError


_OTHER_SOURCE = re.compile(r"^otherMaterials\[([0-9]+)\]$")


def _source_text(request, key):
    if key == "plaintiffComplaint":
        return request.plaintiffComplaint
    if key == "defendantAnswer":
        return request.defendantAnswer
    match = _OTHER_SOURCE.fullmatch(key)
    if match and int(match.group(1)) < len(request.otherMaterials):
        return request.otherMaterials[int(match.group(1))].text
    raise ValueError("sourceKey does not identify an input document")


def _pointer_value(draft, pointer):
    value = draft
    for part in pointer.removeprefix("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            value = value[part]
        elif isinstance(value, list):
            value = value[int(part)]
        else:
            raise ValueError("fieldPath is not a draft field")
    return value


def validate_civil_draft_agent_output(raw_output, request):
    """Reject malformed output, invented source references and uncited key material."""
    try:
        if not isinstance(raw_output, str):
            raise ValueError("output type")
        data = strict_json(raw_output, max_bytes=CIVIL_DRAFT_RESPONSE_MAX_BYTES)
        response = CivilCaseDraftGenerateResponseV1.model_validate(data)
        draft = response.draft.model_dump(mode="json")
        cited_paths = set()
        for ref in response.sourceRefs:
            _pointer_value(draft, ref.fieldPath)
            if ref.quote not in _source_text(request, ref.sourceKey):
                raise ValueError("source quote not found in input")
            cited_paths.add(ref.fieldPath)
        for issue in response.issues:
            for ref in issue.sources:
                if ref.quote not in _source_text(request, ref.sourceKey):
                    raise ValueError("issue source quote not found in input")
        required_paths = {
            f"/claims/{index}/text" for index in range(len(response.draft.claims))
        }
        required_paths.update(
            f"/defenses/{index}" for index in range(len(response.draft.defenses))
        )
        required_paths.update(
            f"/evidenceGroups/{group_index}/materials/{material_index}/displayText"
            for group_index, group in enumerate(response.draft.evidenceGroups)
            for material_index in range(len(group.materials))
        )
        if not required_paths <= cited_paths:
            raise ValueError("a claim, defense or evidence excerpt lacks a source reference")
    except (ValidationError, TypeError, ValueError, KeyError, IndexError, UnicodeError, RecursionError) as exc:
        field = "response"
        if isinstance(exc, ValidationError):
            field = ".".join(str(part) for part in exc.errors()[0]["loc"]) or field
        raise CivilDraftInvalidResponseError(
            params={"reason": "schema_or_source_validation_failed", "field": field},
            cause=exc,
        ) from exc
    if len(response.model_dump_json().encode("utf-8")) > CIVIL_DRAFT_RESPONSE_MAX_BYTES:
        raise CivilDraftInvalidResponseError(
            params={"reason": "response_size", "field": "response"}
        )
    return response

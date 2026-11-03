"""Validate generated civil draft JSON against the response contract."""

from pydantic import ValidationError

from app.schemas.integrations.strict_json import strict_json
from app.schemas.integrations.virtual_court import CivilCaseDraftGenerateResponseV2
from app.schemas.integrations.virtual_court.civil_case_draft import CIVIL_DRAFT_RESPONSE_MAX_BYTES

from .exceptions import CivilDraftInvalidResponseError


def validate_civil_draft_agent_output(raw_output, request=None):
    """Reject malformed output and unsupported response fields."""
    try:
        if not isinstance(raw_output, str):
            raise ValueError("output type")
        data = strict_json(raw_output, max_bytes=CIVIL_DRAFT_RESPONSE_MAX_BYTES)
        response = CivilCaseDraftGenerateResponseV2.model_validate(data)
        if request is not None:
            validate_segment_coverage(response, request)
    except (ValidationError, TypeError, ValueError, KeyError, IndexError, UnicodeError, RecursionError) as exc:
        field = str(exc)[:800] if isinstance(exc, ValueError) else "response"
        if isinstance(exc, ValidationError):
            field = ".".join(str(part) for part in exc.errors()[0]["loc"]) or field
        raise CivilDraftInvalidResponseError(
            params={"reason": "schema_validation_failed", "field": field},
            cause=exc,
        ) from exc
    return response


def validate_segment_coverage(response, request):
    """Match the expanded requested names and roles, without positional guesses."""
    expected = {}
    groups = response.draft.evidenceGroups
    group_keys = [(item.side, item.name) for item in groups]
    if len(group_keys) != len(set(group_keys)):
        raise ValueError("duplicate evidence group name for side")
    for phase in request.procedure.phases:
        for step in phase.steps:
            for segment in step.segments:
                targets = groups if step.type == "evidenceGroupLoop" else [None]
                for group in targets:
                    name, role = segment.name, segment.speakerRole
                    if group is not None:
                        offering = group.side
                        opposing = "defendant" if offering == "plaintiff" else "plaintiff"
                        name = name.replace("{举证方}", "原告" if offering == "plaintiff" else "被告")
                        name = name.replace("{质证方}", "原告" if opposing == "plaintiff" else "被告")
                        name = name.replace("{证据组名称}", group.name)
                        role = offering if role == "offeringParty" else opposing if role == "opposingParty" else role
                    if " / " in name or "{" in name or "}" in name:
                        raise ValueError("expanded segment name contains reserved characters")
                    key = (step.name, name)
                    if key in expected:
                        raise ValueError("expanded segment names collide")
                    expected[key] = role
    seen = set()
    blocking = any(item.severity == "blocking" for item in response.issues)
    for item in response.draft.segmentContents:
        key = (item.stepName, item.segmentName)
        if key in seen or expected.get(key) != item.speakerRole:
            raise ValueError("duplicate, unrequested or wrong-role segment: " + " / ".join(key))
        if not item.text.strip() and not blocking:
            raise ValueError("empty segment text requires a blocking issue")
        seen.add(key)
    if seen != set(expected):
        raise ValueError("missing requested segments: " + repr(sorted(set(expected) - seen)))

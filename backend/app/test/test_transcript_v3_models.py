"""TranscriptAPI V3 Pydantic models against the frozen fixture contract."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.integrations.virtual_court import (
    TranscriptGenerateRequestV3,
    TranscriptGenerateResponseV3,
)
from app.schemas.integrations.virtual_court.transcript import (
    TRANSCRIPT_MAX_CODEPOINTS,
    TRANSCRIPT_RESPONSE_MAX_BYTES,
)


ROOT = Path(__file__).parent / "fixtures" / "transcript_v3"


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


MANIFEST = load("manifest.json")
MODEL_REASONS = {"", "schema", "content_budget"}
REQUEST_CASES = [
    case
    for case in MANIFEST["cases"]
    if case["kind"] == "request"
    and case.get("reason", "") in MODEL_REASONS
    and case["id"] not in {
        "transcript-duplicate-key",
        "transcript-markdown-fence",
    }
]
RESPONSE_CASES = [
    case
    for case in MANIFEST["cases"]
    if case["kind"] == "response"
    and case.get("reason", "") in {"", "schema"}
]


@pytest.mark.parametrize("case", REQUEST_CASES, ids=lambda case: case["id"])
def test_request_model_matches_frozen_schema_and_content_cases(case):
    data = load(case["file"])
    if case["valid"]:
        request = TranscriptGenerateRequestV3.model_validate(data)
        assert request.model_dump(mode="json") == data
    else:
        with pytest.raises(ValidationError):
            TranscriptGenerateRequestV3.model_validate(data)


@pytest.mark.parametrize("case", RESPONSE_CASES, ids=lambda case: case["id"])
def test_response_model_matches_frozen_schema_cases(case):
    data = load(case["file"])
    if case["valid"]:
        response = TranscriptGenerateResponseV3.model_validate(data)
        assert response.model_dump(mode="json") == data
    else:
        with pytest.raises(ValidationError):
            TranscriptGenerateResponseV3.model_validate(data)


def test_request_uses_virtual_court_transcript_domain_names():
    fields = TranscriptGenerateRequestV3.model_fields
    assert set(fields) == {
        "state_version", "case_info", "participants", "records",
    }


def test_contract_exports_only_the_minimal_top_level_fields():
    assert set(TranscriptGenerateRequestV3.model_fields) == {
        "state_version",
        "case_info",
        "participants",
        "records",
    }
    assert set(TranscriptGenerateResponseV3.model_fields) == {
        "state_version",
        "records",
    }


def test_transcript_limits_match_frozen_metadata():
    limits = load("limits.json")
    assert TRANSCRIPT_MAX_CODEPOINTS == limits["transcript_max_codepoints"]
    assert TRANSCRIPT_RESPONSE_MAX_BYTES == limits["response_body_max_bytes"]


@pytest.mark.parametrize("field,limit", [("stage_name", 256), ("step_name", 256), ("segment_name", 1024)])
def test_record_names_are_required_nonblank_and_bounded(field, limit):
    data = load("cases/transcript-speech-request.json")
    record = data["records"][0]
    for invalid in (None, "", "  ", "字" * (limit + 1)):
        record[field] = invalid
        with pytest.raises(ValidationError):
            TranscriptGenerateRequestV3.model_validate(data)
    record[field] = "😀" * limit
    assert getattr(TranscriptGenerateRequestV3.model_validate(data).records[0], field) == record[field]
    del record[field]
    with pytest.raises(ValidationError):
        TranscriptGenerateRequestV3.model_validate(data)


def test_configured_names_are_not_civil_phase_enums_or_segment_ids():
    data = load("cases/transcript-speech-request.json")
    for index, record in enumerate(data["records"]):
        record.update(stage_name="自定义调查阶段", step_name=f"自定义步骤{index}", segment_name="共同环节")
    request = TranscriptGenerateRequestV3.model_validate(data)
    assert all(record.segment_name == "共同环节" for record in request.records)
    assert request.model_dump(mode="json") == data


@pytest.mark.parametrize("legacy", [{"phase": "court_opening"}, {"step_id": "OPEN-02"}])
def test_legacy_record_fields_are_rejected(legacy):
    data = load("cases/transcript-speech-request.json")
    data["records"][0].update(legacy)
    with pytest.raises(ValidationError):
        TranscriptGenerateRequestV3.model_validate(data)

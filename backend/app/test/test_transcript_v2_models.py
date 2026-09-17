"""TranscriptAPI V2 Pydantic models against the frozen fixture contract."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.integrations.virtual_court import (
    JudgeCaseContext,
    JudgeRecord,
    TranscriptGenerateRequestV2,
    TranscriptGenerateResponseV2,
)
from app.schemas.integrations.virtual_court.transcript import (
    TRANSCRIPT_MAX_CODEPOINTS,
    TRANSCRIPT_RESPONSE_MAX_BYTES,
)


ROOT = Path(__file__).parent / "fixtures" / "transcript_v2"


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
        request = TranscriptGenerateRequestV2.model_validate(data)
        assert request.model_dump(mode="json") == data
    else:
        with pytest.raises(ValidationError):
            TranscriptGenerateRequestV2.model_validate(data)


@pytest.mark.parametrize("case", RESPONSE_CASES, ids=lambda case: case["id"])
def test_response_model_matches_frozen_schema_cases(case):
    data = load(case["file"])
    if case["valid"]:
        response = TranscriptGenerateResponseV2.model_validate(data)
        assert response.model_dump(mode="json") == data
    else:
        with pytest.raises(ValidationError):
            TranscriptGenerateResponseV2.model_validate(data)


def test_request_reuses_judge_material_models():
    fields = TranscriptGenerateRequestV2.model_fields
    assert fields["case_context"].annotation is JudgeCaseContext
    assert fields["records"].annotation == list[JudgeRecord]


def test_contract_exports_only_the_minimal_top_level_fields():
    assert set(TranscriptGenerateRequestV2.model_fields) == {
        "state_version",
        "case_context",
        "records",
    }
    assert set(TranscriptGenerateResponseV2.model_fields) == {
        "state_version",
        "transcript",
    }


def test_transcript_limits_match_frozen_metadata():
    limits = load("limits.json")
    assert TRANSCRIPT_MAX_CODEPOINTS == limits["transcript_max_codepoints"]
    assert TRANSCRIPT_RESPONSE_MAX_BYTES == limits["response_body_max_bytes"]

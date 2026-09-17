import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api.integrations.strict_json_route import REQUEST_MAX_BYTES
from app.schemas.integrations.strict_json import strict_json
from app.schemas.integrations.virtual_court import (
    JudgeLawCheckRequestV2,
    JudgeLawCheckResponseV2,
    JudgeNextActionRequestV2,
    JudgeNextActionResponseV2,
)
from app.schemas.integrations.virtual_court.judge import (
    RESPONSE_MAX_BYTES,
)


ROOT = Path(__file__).parent / "fixtures" / "judge_v2_split_endpoints"
MODELS = {
    "law-check-request": JudgeLawCheckRequestV2,
    "law-check-response": JudgeLawCheckResponseV2,
    "next-action-request": JudgeNextActionRequestV2,
    "next-action-response": JudgeNextActionResponseV2,
}


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


CASES = [
    case
    for case in load("manifest.json")["cases"]
    if case.get("reason") not in {
        "decision_not_allowed",
        "target_not_allowed",
        "stale_state",
    }
]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_split_models_match_frozen_examples(case):
    raw = (ROOT / case["file"]).read_bytes()
    limit = REQUEST_MAX_BYTES if case["kind"] == "request" else RESPONSE_MAX_BYTES

    def validate():
        data = strict_json(raw, max_bytes=limit)
        return MODELS[case["schema"]].model_validate(data)

    if case["valid"]:
        validate()
    else:
        with pytest.raises((ValueError, ValidationError)):
            validate()


def test_law_check_context_defaults_to_empty_string():
    request = JudgeLawCheckRequestV2(
        state_version=1,
        role="PLAINTIFF",
        text="没有需要解释的法律问题。",
    )
    assert request.context == ""


def test_split_models_have_exact_wire_fields():
    assert set(JudgeLawCheckRequestV2.model_fields) == {
        "state_version", "role", "text", "context"
    }
    assert set(JudgeLawCheckResponseV2.model_fields) == {
        "state_version", "decision", "speech", "pending_points"
    }
    assert set(JudgeNextActionRequestV2.model_fields) == {
        "state_version", "allowed_actions", "allowed_targets",
        "case_context", "records",
    }
    assert set(JudgeNextActionResponseV2.model_fields) == {
        "state_version", "decision", "target", "speech", "pending_points"
    }


def test_unicode_limit_counts_code_points_not_utf8_bytes():
    request = JudgeLawCheckRequestV2(
        state_version=1,
        role="DEFENDANT",
        text="法" * 8000,
    )
    assert len(request.text) == 8000
    with pytest.raises(ValidationError):
        JudgeLawCheckRequestV2(
            state_version=1,
            role="DEFENDANT",
            text="法" * 8001,
        )


def test_raw_body_limit_counts_utf8_bytes():
    strict_json(b" " * (REQUEST_MAX_BYTES - 2) + b"{}", max_bytes=REQUEST_MAX_BYTES)
    with pytest.raises(ValueError, match="body_size"):
        strict_json(b" " * (REQUEST_MAX_BYTES - 1) + b"{}", max_bytes=REQUEST_MAX_BYTES)

"""Strict transcript-agent output validation."""

import json

import pytest

from app.schemas.integrations.virtual_court import TranscriptGenerateRequestV2
from app.services.virtual_court import (
    TranscriptInvalidResponseError,
    validate_transcript_agent_output,
)


def request():
    return TranscriptGenerateRequestV2(
        state_version=42,
        case_context={
            "summary": "测试案件。",
            "claims": [],
            "defenses": [],
            "dispute_focuses": [],
        },
        records=[
            {"type": "SPEECH", "role": "JUDGE", "text": "现在开庭。"}
        ],
    )


def output(transcript="庭审笔录\n\n审判员：现在开庭。", **changes):
    data = {"transcript": transcript}
    data.update(changes)
    return json.dumps(data, ensure_ascii=False)


def test_valid_output_receives_trusted_state_version():
    response = validate_transcript_agent_output(output(), request())
    assert response.state_version == 42
    assert response.transcript.startswith("庭审笔录")


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "{}",
        "```json\n{\"transcript\":\"笔录\"}\n```",
        '{"transcript":"甲","transcript":"乙"}',
        output(transcript="   "),
        output(state_version=999),
        output(warnings=[]),
    ],
)
def test_invalid_agent_output_is_rejected(raw):
    with pytest.raises(TranscriptInvalidResponseError) as captured:
        validate_transcript_agent_output(raw, request())
    assert captured.value.params["reason"] == "schema_validation_failed"


def test_transcript_over_codepoint_limit_is_rejected():
    with pytest.raises(TranscriptInvalidResponseError) as captured:
        validate_transcript_agent_output(
            output(transcript="录" * 64001),
            request(),
        )
    assert captured.value.params == {
        "reason": "schema_validation_failed",
        "field": "transcript",
    }


def test_validation_error_does_not_expose_raw_output():
    secret = "private-model-output"
    with pytest.raises(TranscriptInvalidResponseError) as captured:
        validate_transcript_agent_output(secret, request())
    assert secret not in str(captured.value.params)

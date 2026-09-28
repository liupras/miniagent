"""Strict transcript-organizer output validation."""

import json

import pytest

from app.schemas.integrations.virtual_court import TranscriptGenerateRequestV2
from app.services.virtual_court import (
    TranscriptInvalidResponseError,
    validate_transcript_agent_output,
)


def request():
    return TranscriptGenerateRequestV2.model_validate({
        "state_version": 42,
        "case_info": {
            "case_id": "case-01",
            "case_number": "（2026）虚法民初01号",
            "court_name": "虚拟人民法院",
            "procedure": "民事一审简易程序",
            "cause_of_action": "著作权侵权纠纷",
            "subject_matter": "《山海鹿鸣》",
            "is_simulated": True,
            "legal_effect_disclaimer": "模拟案件，不产生司法效力。",
        },
        "participants": [{
            "participant_id": "judge-01", "role": "judge",
            "display_name": "张某某", "description": "独任审判员",
        }],
        "records": [{
            "sequence": 1, "step_id": "OPEN-02", "phase": "court_opening",
            "role": "judge", "text": "现在，嗯，开庭。", "is_intervention": False,
        }],
    })


def output(text="现在开庭。", sequence=1, **changes):
    data = {"records": [{"sequence": sequence, "text": text}]}
    data.update(changes)
    return json.dumps(data, ensure_ascii=False)


def test_valid_output_receives_trusted_state_version():
    response = validate_transcript_agent_output(output(), request())
    assert response.state_version == 42
    assert response.records[0].sequence == 1
    assert response.records[0].text == "现在开庭。"


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "{}",
        "```json\n{\"records\":[]}\n```",
        '{"records":[],"records":[]}',
        output(text="   "),
        output(sequence=2),
        output(state_version=999),
        output(warnings=[]),
    ],
)
def test_invalid_agent_output_is_rejected(raw):
    with pytest.raises(TranscriptInvalidResponseError) as captured:
        validate_transcript_agent_output(raw, request())
    assert captured.value.params["reason"] == "schema_validation_failed"


def test_reordered_or_missing_sequences_are_rejected():
    req = request().model_copy(deep=True)
    req.records.append(req.records[0].model_copy(update={"sequence": 2}))
    for records in (
        [{"sequence": 2, "text": "二"}, {"sequence": 1, "text": "一"}],
        [{"sequence": 1, "text": "一"}],
    ):
        with pytest.raises(TranscriptInvalidResponseError):
            validate_transcript_agent_output(
                json.dumps({"records": records}, ensure_ascii=False), req
            )


def test_record_text_over_codepoint_limit_is_rejected():
    with pytest.raises(TranscriptInvalidResponseError) as captured:
        validate_transcript_agent_output(output(text="录" * 8001), request())
    assert captured.value.params["reason"] == "schema_validation_failed"


def test_validation_error_does_not_expose_raw_output():
    secret = "private-model-output"
    with pytest.raises(TranscriptInvalidResponseError) as captured:
        validate_transcript_agent_output(secret, request())
    assert secret not in str(captured.value.params)

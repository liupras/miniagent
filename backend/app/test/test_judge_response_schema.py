import json

import pytest

from app.schemas.integrations.virtual_court import (
    JudgeAgentOutput,
    JudgeDecisionRequest,
    judge_agent_output_json_schema,
)
from app.services.virtual_court import (
    JudgeInvalidResponseError,
    validate_judge_agent_output,
)


def _request(**overrides) -> JudgeDecisionRequest:
    data = {
        "state_version": 18,
        "current_stage": "COURT_INVESTIGATION",
        "current_step": "INQUIRY-D-A",
        "trigger": "CLARIFICATION_NEEDED",
        "task": "要求被告明确回答是否核验过商用授权。",
        "current_speaker": "DEFENDANT",
        "allowed_actions": ["REQUEST_CLARIFICATION"],
        "allowed_targets": ["DEFENDANT"],
        "case_context": {
            "cause_of_action": "著作权侵权纠纷",
            "procedure": "民事一审简易程序",
            "summary": "原告主张被告未经许可使用涉案插画。",
        },
    }
    data.update(overrides)
    return JudgeDecisionRequest.model_validate(data)


def _valid_output_data() -> dict:
    return {
        "speech": {
            "type": "CLARIFICATION",
            "text": "被告，请明确回答使用前是否核验过商用授权。",
            "target_role": "DEFENDANT",
        },
        "action": {
            "type": "REQUEST_CLARIFICATION",
            "target_role": "DEFENDANT",
        },
        "legal_citations": [],
        "confidence": "HIGH",
        "warnings": [],
    }


def test_strict_output_accepts_exact_json_and_injects_state_version():
    response = validate_judge_agent_output(
        json.dumps(_valid_output_data(), ensure_ascii=False),
        _request(),
    )

    assert response.state_version == 18
    assert response.action.type.value == "REQUEST_CLARIFICATION"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.update({"state_version": 999}),
        lambda data: data.pop("warnings"),
        lambda data: data.update({"unknown": True}),
        lambda data: data.update({"requires_human_review": False}),
        lambda data: data["speech"].update({"text": 123}),
    ],
)
def test_strict_output_rejects_extra_missing_and_coerced_fields(mutate):
    data = _valid_output_data()
    mutate(data)

    with pytest.raises(JudgeInvalidResponseError) as caught:
        validate_judge_agent_output(
            json.dumps(data, ensure_ascii=False),
            _request(),
        )
    assert caught.value.params["reason"] == "schema_validation_failed"


def test_strict_output_rejects_markdown_fences():
    raw = f"```json\n{json.dumps(_valid_output_data(), ensure_ascii=False)}\n```"

    with pytest.raises(JudgeInvalidResponseError) as caught:
        validate_judge_agent_output(raw, _request())
    assert caught.value.params["reason"] == "schema_validation_failed"


def test_strict_output_rejects_an_action_not_allowed_by_request():
    data = _valid_output_data()
    data["speech"] = {
        "type": "PROCEDURAL_DIRECTION",
        "text": "现在进入下一步骤。",
        "target_role": None,
    }
    data["action"] = {"type": "ADVANCE_STEP", "target_role": None}

    with pytest.raises(JudgeInvalidResponseError) as caught:
        validate_judge_agent_output(
            json.dumps(data, ensure_ascii=False),
            _request(),
        )
    assert caught.value.params["reason"] == "action_not_allowed"


def test_strict_output_rejects_a_target_not_allowed_by_request():
    data = _valid_output_data()
    data["speech"]["target_role"] = "PLAINTIFF"
    data["action"]["target_role"] = "PLAINTIFF"

    with pytest.raises(JudgeInvalidResponseError) as caught:
        validate_judge_agent_output(
            json.dumps(data, ensure_ascii=False),
            _request(),
        )
    assert caught.value.params["reason"] == "target_not_allowed"


def test_output_schema_requires_every_top_level_field_and_forbids_extras():
    schema = judge_agent_output_json_schema()

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(JudgeAgentOutput.model_fields)
    for definition in schema["$defs"].values():
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False
            assert set(definition["required"]) == set(definition["properties"])

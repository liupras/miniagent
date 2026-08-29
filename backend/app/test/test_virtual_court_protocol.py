import pytest
from pydantic import ValidationError

from app.schemas.integrations.virtual_court import (
    ActionType,
    CaseContext,
    ConfidenceLevel,
    CourtEvent,
    JudgeActionProposal,
    JudgeDecisionRequest,
    JudgeDecisionResponse,
    JudgeSpeech,
    PartyRole,
    SpeechType,
    StageSummary,
    TriggerType,
)


def _request_data() -> dict:
    return {
        "state_version": 18,
        "current_stage": "COURT_INVESTIGATION",
        "current_step": "INQUIRY-D-A",
        "trigger": "CLARIFICATION_NEEDED",
        "task": "要求被告明确说明使用图片前是否核验过商用授权。",
        "current_speaker": "DEFENDANT",
        "allowed_actions": ["NO_ACTION", "REQUEST_CLARIFICATION"],
        "allowed_targets": ["DEFENDANT"],
        "case_context": {
            "cause_of_action": "著作权侵权纠纷",
            "procedure": "民事一审简易程序",
            "summary": "原告主张被告未经许可将插画用于商业宣传。",
            "dispute_focuses": ["被告使用涉案作品是否构成侵权"],
        },
        "recent_events": [
            {
                "event_type": "PARTY_SPEECH_CONFIRMED",
                "actor": "DEFENDANT",
                "step_id": "INQUIRY-D-A",
                "content": "工作人员认为公开下载的图片可以使用。",
            }
        ],
    }


def test_judge_decision_request_accepts_a_self_contained_payload():
    request = JudgeDecisionRequest.model_validate(_request_data())

    assert request.trigger == TriggerType.CLARIFICATION_NEEDED
    assert request.allowed_actions == [
        ActionType.NO_ACTION,
        ActionType.REQUEST_CLARIFICATION,
    ]
    assert request.allowed_targets == [PartyRole.DEFENDANT]
    assert request.recent_events[0].actor.value == "DEFENDANT"


def test_judge_decision_request_rejects_unknown_fields():
    data = _request_data()
    data["conversation_history"] = []

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        JudgeDecisionRequest.model_validate(data)


def test_judge_decision_request_rejects_removed_script_guidance():
    data = _request_data()
    data["script_guidance"] = {
        "step_class": "A",
        "objective": "澄清被告是否核验商用授权。",
        "resume_step_id": "INQUIRY-D-A",
    }

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        JudgeDecisionRequest.model_validate(data)


def test_party_action_requires_an_allowed_target():
    data = _request_data()
    data["allowed_targets"] = []

    with pytest.raises(ValidationError, match="allowed_targets is required"):
        JudgeDecisionRequest.model_validate(data)


def test_allowed_actions_must_not_contain_duplicates():
    data = _request_data()
    data["allowed_actions"] = ["NO_ACTION", "NO_ACTION"]

    with pytest.raises(ValidationError, match="must not contain duplicates"):
        JudgeDecisionRequest.model_validate(data)


def test_legal_explanation_without_citations_is_marked_insufficient():
    response = JudgeDecisionResponse(
        state_version=18,
        speech=JudgeSpeech(
            type=SpeechType.LEGAL_EXPLANATION,
            text="当前知识库未检索到足够依据。",
            target_role=None,
        ),
        action=JudgeActionProposal(type=ActionType.NO_ACTION, target_role=None),
        legal_citations=[],
        confidence=ConfidenceLevel.INSUFFICIENT,
        warnings=["未检索到可核验的法律依据"],
    )

    assert response.legal_citations == []


def test_party_action_and_speech_type_must_match():
    with pytest.raises(ValidationError, match="requires QUESTION speech"):
        JudgeDecisionResponse(
            state_version=18,
            speech=JudgeSpeech(
                type=SpeechType.CLARIFICATION,
                text="请被告回答。",
                target_role=PartyRole.DEFENDANT,
            ),
            action=JudgeActionProposal(
                type=ActionType.ASK_PARTY,
                target_role=PartyRole.DEFENDANT,
            ),
            legal_citations=[],
            confidence=ConfidenceLevel.HIGH,
            warnings=[],
        )


def test_request_contains_only_reasoning_inputs():
    assert set(JudgeDecisionRequest.model_fields) == {
        "state_version",
        "current_stage",
        "current_step",
        "trigger",
        "task",
        "current_speaker",
        "allowed_actions",
        "allowed_targets",
        "case_context",
        "stage_summaries",
        "recent_events",
    }


def test_response_contains_only_decision_outputs():
    assert set(JudgeDecisionResponse.model_fields) == {
        "state_version",
        "speech",
        "action",
        "legal_citations",
        "confidence",
        "warnings",
    }


def test_context_models_contain_only_reasoning_inputs():
    assert set(CaseContext.model_fields) == {
        "cause_of_action",
        "procedure",
        "summary",
        "claims",
        "defenses",
        "dispute_focuses",
    }
    assert set(StageSummary.model_fields) == {"stage_id", "summary"}
    assert set(CourtEvent.model_fields) == {
        "event_type",
        "actor",
        "step_id",
        "content",
    }

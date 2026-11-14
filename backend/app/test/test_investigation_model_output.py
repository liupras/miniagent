"""Model decisions are checked before HTTP binding fields are restored."""

import copy
import json
from pathlib import Path

import pytest

from app.schemas.integrations.virtual_court.investigation import (
    JudgeNextActionRequest,
    ParticipantIntentRequest,
    ParticipantSpeechRequest,
)
from app.services.virtual_court import InvestigationInvalidResponseError
from app.services.virtual_court.investigation_validator import (
    validate_intent_model_output,
    validate_judge_model_output,
    validate_speech_model_output,
)


EXAMPLES = Path(__file__).parent / "fixtures" / "investigation-v4.examples.json"


def _fixture(name):
    return copy.deepcopy(json.loads(EXAMPLES.read_text(encoding="utf-8"))[name])


def _judge(scope=None):
    data = _fixture("judgeAgentRequest")
    if scope is not None:
        data["scope"] = scope
    data["case_context"]["participants"] = [
        {"participantId": "participant_claimant", "displayName": "原告"}]
    return JudgeNextActionRequest.model_validate(data)


def _raw(value):
    return json.dumps(value, ensure_ascii=False)


def _field(error):
    return error.value.params["field"]


def test_intent_pass_and_request_restore_only_request_binding():
    request = ParticipantIntentRequest.model_validate(_fixture("participantIntentRequest"))
    passed = validate_intent_model_output(_raw({"decision": "pass"}), request)
    assert passed.model_dump(exclude_unset=True) == {
        "investigation_id": request.investigation_id,
        "decision_revision": request.decision_revision,
        "decision": "pass",
    }
    applied = validate_intent_model_output(_raw({
        "decision": "request", "speech_kind": "respond", "topic_id": "other",
    }), request)
    assert applied.decision == "request"
    assert applied.topic_id == "other"
    assert "reason" not in applied.model_fields_set


def test_speech_text_gets_original_investigation_and_turn():
    request = ParticipantSpeechRequest.model_validate(_fixture("participantSpeechRequest"))
    response = validate_speech_model_output(_raw({"speech": "我方就授权来源作补充说明。"}), request)
    assert response.model_dump(exclude_unset=True) == {
        "investigation_id": request.investigation_id,
        "turn_id": request.turn_id,
        "speech": "我方就授权来源作补充说明。",
    }


def test_auto_judge_action_uses_text_utterance_without_scope():
    request = _judge()
    response = validate_judge_model_output(_raw({
        "decision": "action",
        "action": {
            "type": "invite_participant", "participantId": "participant_claimant",
            "speechKind": "answer", "topicId": "topic_authorization",
        },
        "utterance": "请原告说明授权文件形成时间。",
    }), request)
    payload = response.model_dump(mode="json", exclude_unset=True)
    assert payload["investigation_id"] == request.investigation_id
    assert payload["decision_revision"] == request.decision_revision
    assert payload["utterance"] == {
        "mode": "text", "text": "请原告说明授权文件形成时间。",
    }
    assert "scope" not in payload


def test_manual_judge_action_defer_and_handoff_bind_scope():
    selected = JudgeNextActionRequest.model_validate(_fixture("judgeAdviceRequest"))
    action = validate_judge_model_output(_raw({
        "decision": "action",
        "action": {"type": "reject_request", "requestId": selected.request_id},
        "utterance": "本次申请暂不准许。",
    }), selected)
    assert action.scope == "request"
    assert action.action.requestId == selected.request_id
    deferred = validate_judge_model_output(_raw({
        "decision": "defer", "reason": "先核对已有发言。",
    }), selected)
    assert deferred.scope == "request" and deferred.reason == "先核对已有发言。"
    assert "action" not in deferred.model_fields_set

    next_request = _judge("next")
    handoff = validate_judge_model_output(_raw({
        "decision": "handoff", "reason": "现有记录不足。",
    }), next_request)
    assert handoff.scope == "next" and handoff.reason == "现有记录不足。"


def test_summary_requires_spoken_text():
    request = _judge("summary")
    response = validate_judge_model_output(_raw({
        "decision": "action", "action": {"type": "close_investigation"},
        "utterance": "双方已发表意见，争议留待后续审理。",
    }), request)
    assert response.action.type == "close_investigation"
    for text in ("", "  "):
        with pytest.raises(InvestigationInvalidResponseError):
            validate_judge_model_output(_raw({
                "decision": "action", "action": {"type": "close_investigation"},
                "utterance": text,
            }), request)


@pytest.mark.parametrize("raw,expected", [
    ('{"action":{"type":"close_investigation"},"utterance":"结束。"}', "decision"),
    ('{"decision":"action","action":{"type":"close_investigation"},"utterance":"结束。","decision_revision":0}', "decision_revision"),
    ('{"decision":"action","action":{"type":"close_investigation"},"utterance":{"mode":"text","text":"结束。"}}', "utterance"),
    ('{"decision":"action","action":{"type":"close_investigation"},"utterance":"结束。","scope":"summary"}', "scope"),
])
def test_model_cannot_omit_decision_or_echo_http_fields(raw, expected):
    with pytest.raises(InvestigationInvalidResponseError) as error:
        validate_judge_model_output(raw, _judge("summary"))
    assert _field(error) == expected


def test_intent_and_speech_reject_echoed_binding_and_duplicate_keys():
    intent = ParticipantIntentRequest.model_validate(_fixture("participantIntentRequest"))
    speech = ParticipantSpeechRequest.model_validate(_fixture("participantSpeechRequest"))
    for raw, request, validator, expected in (
        ('{"decision":"pass","investigation_id":"inv"}', intent,
         validate_intent_model_output, "investigation_id"),
        ('{"speech":"发言。","turn_id":"turn"}', speech,
         validate_speech_model_output, "turn_id"),
        ('{"decision":"pass","decision":"request"}', intent,
         validate_intent_model_output, "response"),
    ):
        with pytest.raises(InvestigationInvalidResponseError) as error:
            validator(raw, request)
        assert _field(error) == expected


def test_model_choice_must_match_current_case_and_scope():
    intent = ParticipantIntentRequest.model_validate(_fixture("participantIntentRequest"))
    with pytest.raises(InvestigationInvalidResponseError) as error:
        validate_intent_model_output(_raw({
            "decision": "request", "speech_kind": "respond", "topic_id": "unknown",
        }), intent)
    assert _field(error) == "topic_id"

    selected = JudgeNextActionRequest.model_validate(_fixture("judgeAdviceRequest"))
    with pytest.raises(InvestigationInvalidResponseError) as error:
        validate_judge_model_output(_raw({
            "decision": "action",
            "action": {"type": "reject_request", "requestId": "other"},
            "utterance": "不准许。",
        }), selected)
    assert _field(error) == "action.requestId"

    with pytest.raises(InvestigationInvalidResponseError) as error:
        validate_judge_model_output(_raw({
            "decision": "defer", "reason": "稍后处理。",
        }), _judge("next"))
    assert _field(error) == "decision"


def test_judge_cannot_handle_locked_request_or_close_with_pending_request():
    data = _fixture("judgeAdviceRequest")
    data["investigation"]["pendingRequests"][0]["locked"] = True
    selected = JudgeNextActionRequest.model_validate(data)
    with pytest.raises(InvestigationInvalidResponseError) as error:
        validate_judge_model_output(_raw({
            "decision": "action",
            "action": {"type": "grant_request", "requestId": selected.request_id},
            "utterance": "准许发言。",
        }), selected)
    assert _field(error) == "action.requestId"

    data.pop("scope")
    data.pop("request_id")
    automatic = JudgeNextActionRequest.model_validate(data)
    with pytest.raises(InvestigationInvalidResponseError) as error:
        validate_judge_model_output(_raw({
            "decision": "action", "action": {"type": "close_investigation"},
            "utterance": "调查结束。",
        }), automatic)
    assert _field(error) == "action.type"


def test_intent_rejects_normalized_duplicate_request():
    data = _fixture("participantIntentRequest")
    data["investigation"]["pendingRequests"] = [
        {
            "requestId": "request-01", "participantId": data["participant_id"],
            "speechKind": "respond", "topicId": "topic_authorization",
            "reason": "说明 授权来源。", "locked": False,
        }
    ]
    request = ParticipantIntentRequest.model_validate(data)
    with pytest.raises(InvestigationInvalidResponseError) as error:
        validate_intent_model_output(_raw({
            "decision": "request", "speech_kind": "respond",
            "topic_id": "topic_authorization", "reason": "说明授权来源",
        }), request)
    assert _field(error) == "decision"

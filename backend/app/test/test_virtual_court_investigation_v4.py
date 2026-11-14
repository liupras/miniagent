"""Cross-project V4 investigation contract tests."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.integrations.virtual_court.investigation import (
    JudgeNextActionRequest, ParticipantIntentRequest, ParticipantSpeechRequest,
)
from app.services.virtual_court import InvestigationInvalidResponseError
from app.services.virtual_court.investigation_validator import (
    validate_intent_output, validate_judge_output, validate_speech_output,
)


EXAMPLES = Path(__file__).parent / "fixtures" / "investigation-v4.examples.json"


def fixtures():
    return json.loads(EXAMPLES.read_text(encoding="utf-8"))


def test_v4_examples_accept_current_requests_and_responses():
    data = fixtures()
    intent = ParticipantIntentRequest.model_validate(data["participantIntentRequest"])
    speech = ParticipantSpeechRequest.model_validate(data["participantSpeechRequest"])
    judge = JudgeNextActionRequest.model_validate(data["judgeAgentRequest"])
    assert validate_intent_output(json.dumps(data["participantIntentPassResponse"]), intent).decision == "pass"
    speech_result = dict(data["participantSpeechResponse"], turn_id=speech.turn_id)
    assert validate_speech_output(json.dumps(speech_result), speech).speech
    judge_result = dict(data["judgeAgentResponse"], decision_revision=judge.decision_revision)
    assert validate_judge_output(json.dumps(judge_result), judge).utterance.text.startswith("请原告")


def test_request_reason_optional_and_evidence_is_global_context():
    request = ParticipantIntentRequest.model_validate(fixtures()["participantIntentRequest"])
    result = validate_intent_output(json.dumps({
        "investigation_id": request.investigation_id,
        "decision_revision": request.decision_revision,
        "decision": "request", "speech_kind": "examine_evidence", "topic_id": "other",
    }), request)
    assert result.reason is None
    for extra in ({"evidence_group_ids": []}, {"reply_to_turn_id": None}):
        with pytest.raises(InvestigationInvalidResponseError):
            validate_intent_output(json.dumps({
                "investigation_id": request.investigation_id,
                "decision_revision": request.decision_revision,
                "decision": "request", "speech_kind": "supplement", "topic_id": "other",
                **extra,
            }), request)


def test_judge_advice_uses_utterance_and_rejects_old_actions():
    data = fixtures()
    request = JudgeNextActionRequest.model_validate(data["judgeAdviceRequest"])
    answer = dict(data["judgeAdviceResponse"], decision_revision=request.decision_revision)
    assert validate_judge_output(json.dumps(answer), request).utterance.text == "本次申请暂不准许。"
    for action in (
        {"type": "grant_request", "requestId": request.request_id, "evidenceGroupIds": []},
        {"type": "set_context", "topicId": "topic_authorization", "evidenceGroupIds": []},
        {"type": "ask_participant", "participantId": "participant_defense", "text": "请说明。"},
    ):
        with pytest.raises(InvestigationInvalidResponseError):
            validate_judge_output(json.dumps(answer | {"action": action}), request)
    with pytest.raises(InvestigationInvalidResponseError):
        validate_judge_output(json.dumps({k: v for k, v in answer.items() if k != "utterance"}), request)


def test_answer_is_a_scheduled_speech_kind_and_summary_must_be_spoken():
    data = fixtures()["judgeAgentRequest"]
    request = JudgeNextActionRequest.model_validate(data)
    base = {"investigation_id": request.investigation_id,
            "decision_revision": request.decision_revision, "decision": "action"}
    invite = {"type": "invite_participant", "participantId": "participant_claimant",
              "speechKind": "answer"}
    # This example has no participants, so add the person whom the judge will invite.
    data["case_context"]["participants"] = [
        {"participantId": "participant_claimant", "displayName": "原告"}]
    request = JudgeNextActionRequest.model_validate(data)
    assert validate_judge_output(json.dumps(base | {"action": invite,
        "utterance": {"mode": "text", "text": "请说明授权文件形成时间。"}}), request).action.speechKind == "answer"
    with pytest.raises(InvestigationInvalidResponseError):
        validate_judge_output(json.dumps(base | {"action": {"type": "close_investigation"},
            "utterance": {"mode": "text", "text": ""}}), request)


def test_old_request_fields_are_rejected():
    data = fixtures()["participantSpeechRequest"]
    data["investigation"]["activeTurn"]["taskText"] = "回答指定问题"
    with pytest.raises(ValidationError):
        ParticipantSpeechRequest.model_validate(data)

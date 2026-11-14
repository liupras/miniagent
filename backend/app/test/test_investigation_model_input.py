"""The model receives only the V4 investigation inference projection."""

import copy
import json
from pathlib import Path

from app.schemas.integrations.virtual_court.investigation import (
    JudgeNextActionRequest,
    ParticipantIntentRequest,
    ParticipantSpeechRequest,
)
from app.services.virtual_court.investigation_model_input import (
    build_intent_model_input,
    build_judge_model_input,
    build_speech_model_input,
)


EXAMPLES = Path(__file__).parent / "fixtures" / "investigation-v4.examples.json"
FORBIDDEN_MODEL_KEYS = {
    "investigation_id", "investigationId", "decision_revision",
    "decisionRevision", "turn_id", "turnId", "sequence", "sourceRequestId",
    "evidenceGroupId", "displayedEvidenceGroupIds", "status", "activeTurn",
}


def _fixture(name):
    return copy.deepcopy(json.loads(EXAMPLES.read_text(encoding="utf-8"))[name])


def _keys(value):
    if isinstance(value, dict):
        return set(value) | set().union(*(_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_keys(item) for item in value))
    return set()


def _assert_shared_projection(source, projected):
    assert set(projected) >= {"case_context", "records"}
    context = projected["case_context"]
    assert set(context) == {"summary", "participants", "positions", "topics", "evidenceGroups"}
    assert context["summary"] == source.case_context.summary
    assert context["participants"] == [
        {"participantId": p.participantId, "displayName": p.displayName}
        for p in source.case_context.participants
    ]
    assert context["evidenceGroups"] == [
        {
            "offeringParticipantId": e.offeringParticipantId,
            "name": e.name,
            "proofPurpose": e.proofPurpose,
            "materials": list(e.materials),
        }
        for e in source.case_context.evidenceGroups
    ]
    assert len(projected["records"]) == len(source.records)
    assert not (_keys(projected) & FORBIDDEN_MODEL_KEYS)


def test_intent_projection_keeps_current_turn_and_pending_meaning():
    data = _fixture("participantIntentRequest")
    data["investigation"]["pendingRequests"] = [
        {
            "requestId": "request-01", "participantId": "participant_claimant",
            "speechKind": "supplement", "topicId": "topic_authorization",
            "reason": "补充说明。", "locked": True,
        }
    ]
    request = ParticipantIntentRequest.model_validate(data)
    projected = build_intent_model_input(request)
    _assert_shared_projection(request, projected)
    assert set(projected) == {
        "case_context", "records", "participant_id", "current_topic_id",
        "current_turn", "pending_requests",
    }
    assert projected["participant_id"] == request.participant_id
    assert projected["current_topic_id"] == request.investigation.currentTopicId
    assert projected["current_turn"] == {
        "speakerId": "participant_claimant", "kind": "participant",
        "speechKind": "present_evidence", "topicId": "topic_authorization",
    }
    assert projected["pending_requests"] == [
        {
            "participantId": "participant_claimant", "speechKind": "supplement",
            "topicId": "topic_authorization", "reason": "补充说明。",
        }
    ]
    assert projected["records"] == [
        {
            "speakerId": "judge", "kind": "announcement",
            "topicId": "topic_authorization", "text": "请原告就图片授权来源发言。",
        },
        {
            "speakerId": "participant_claimant", "kind": "participant",
            "speechKind": "present_evidence", "topicId": "topic_authorization",
            "text": "我方说明网页截图中图片的使用情况。",
        },
    ]


def test_intent_ready_projection_has_no_current_turn():
    data = _fixture("participantIntentRequest")
    data["investigation"]["status"] = "ready"
    data["investigation"]["activeTurn"] = None
    request = ParticipantIntentRequest.model_validate(data)
    assert build_intent_model_input(request)["current_turn"] is None


def test_intent_announcement_projection_does_not_expose_planned_action():
    data = _fixture("participantIntentRequest")
    data["investigation"]["activeTurn"] = {
        "turnId": "judge-turn-01", "speakerId": "judge", "kind": "announcement",
        "topicId": "topic_authorization",
        "plannedAction": {
            "type": "invite_participant", "participantId": "participant_claimant",
            "speechKind": "answer",
        },
        "sourceRequestId": None,
    }
    request = ParticipantIntentRequest.model_validate(data)
    assert build_intent_model_input(request)["current_turn"] == {
        "speakerId": "judge", "kind": "announcement",
    }


def test_speech_projection_uses_authorized_turn_without_request_queue():
    data = _fixture("participantSpeechRequest")
    data["records"] = [
        {
            "sequence": 1, "turnId": "judge-turn-01", "speakerId": "judge",
            "kind": "announcement", "topicId": "topic_authorization",
            "text": "请被告说明授权来源。", "sourceRequestId": None,
        }
    ]
    request = ParticipantSpeechRequest.model_validate(data)
    projected = build_speech_model_input(request)
    _assert_shared_projection(request, projected)
    assert set(projected) == {
        "case_context", "records", "participant_id", "speech_kind", "topic_id",
    }
    assert projected["participant_id"] == request.participant_id
    assert projected["speech_kind"] == request.investigation.activeTurn.speechKind
    assert projected["topic_id"] == request.investigation.activeTurn.topicId
    assert projected["records"] == [
        {
            "speakerId": "judge", "kind": "announcement",
            "topicId": "topic_authorization", "text": "请被告说明授权来源。",
        }
    ]


def test_judge_projection_distinguishes_auto_and_advice_scope():
    auto = JudgeNextActionRequest.model_validate(_fixture("judgeAgentRequest"))
    projected_auto = build_judge_model_input(auto)
    _assert_shared_projection(auto, projected_auto)
    assert set(projected_auto) == {
        "case_context", "records", "scope", "current_topic_id", "pending_requests",
    }
    assert projected_auto["scope"] == "auto"
    assert projected_auto["pending_requests"] == []

    selected = JudgeNextActionRequest.model_validate(_fixture("judgeAdviceRequest"))
    projected_selected = build_judge_model_input(selected)
    _assert_shared_projection(selected, projected_selected)
    assert projected_selected["scope"] == "request"
    assert projected_selected["selected_request_id"] == selected.request_id
    assert projected_selected["pending_requests"] == [
        {
            "requestId": "request_01", "participantId": "participant_defense",
            "speechKind": "respond", "topicId": "topic_authorization",
            "reason": "", "locked": False,
        }
    ]
    for scope in ("next", "summary"):
        data = _fixture("judgeAgentRequest")
        data["scope"] = scope
        advice = JudgeNextActionRequest.model_validate(data)
        projected = build_judge_model_input(advice)
        assert projected["scope"] == scope
        assert "selected_request_id" not in projected

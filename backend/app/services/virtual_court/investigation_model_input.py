"""Project validated V4 HTTP requests into the investigation model contract.

The HTTP request retains room binding fields. The model sees only the facts and
choices needed for its particular decision.
"""

from app.schemas.integrations.virtual_court.investigation import (
    JudgeNextActionRequest,
    ParticipantIntentRequest,
    ParticipantSpeechRequest,
)


def _common(request):
    context = request.case_context
    return {
        "case_context": {
            "summary": context.summary,
            "participants": [
                {"participantId": item.participantId, "displayName": item.displayName}
                for item in context.participants
            ],
            "positions": [
                {"participantId": item.participantId, "text": item.text}
                for item in context.positions
            ],
            "topics": [
                {"topicId": item.topicId, "text": item.text}
                for item in context.topics
            ],
            "evidenceGroups": [
                {
                    "offeringParticipantId": item.offeringParticipantId,
                    "name": item.name,
                    "proofPurpose": item.proofPurpose,
                    "materials": list(item.materials),
                }
                for item in context.evidenceGroups
            ],
        },
        "records": [
            {
                "speakerId": item.speakerId,
                "kind": item.kind,
                "text": item.text,
                **({"topicId": item.topicId} if item.topicId is not None else {}),
                **({"speechKind": item.speechKind} if item.speechKind is not None else {}),
            }
            for item in request.records
        ],
    }


def build_intent_model_input(request: ParticipantIntentRequest) -> dict:
    """Give an eligible party its identity, current turn and pending intentions."""
    result = _common(request)
    turn = request.investigation.activeTurn
    current_turn = None
    if turn is not None:
        current_turn = {"speakerId": turn.speakerId, "kind": turn.kind}
        if turn.kind == "participant":
            current_turn["speechKind"] = turn.speechKind
            current_turn["topicId"] = turn.topicId
    result.update({
        "participant_id": request.participant_id,
        "current_topic_id": request.investigation.currentTopicId,
        "current_turn": current_turn,
        "pending_requests": [
            {
                "participantId": item.participantId,
                "speechKind": item.speechKind,
                "topicId": item.topicId,
                "reason": item.reason,
            }
            for item in request.investigation.pendingRequests
        ],
    })
    return result


def build_speech_model_input(request: ParticipantSpeechRequest) -> dict:
    """Give a speaker its authorized speech kind and topic, without turn IDs."""
    result = _common(request)
    turn = request.investigation.activeTurn
    if turn is None or turn.kind != "participant":
        raise ValueError("participant speech requires an active participant turn")
    result.update({
        "participant_id": request.participant_id,
        "speech_kind": turn.speechKind,
        "topic_id": turn.topicId,
    })
    return result


def build_judge_model_input(request: JudgeNextActionRequest) -> dict:
    """Give the judge its scope, current topic and actionable request context."""
    result = _common(request)
    result.update({
        "scope": request.scope or "auto",
        "current_topic_id": request.investigation.currentTopicId,
        "pending_requests": [
            {
                "requestId": item.requestId,
                "participantId": item.participantId,
                "speechKind": item.speechKind,
                "topicId": item.topicId,
                "reason": item.reason,
                "locked": item.locked,
            }
            for item in request.investigation.pendingRequests
        ],
    })
    if request.scope == "request":
        result["selected_request_id"] = request.request_id
    return result

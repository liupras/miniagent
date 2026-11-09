"""Validate untrusted outputs from the three new investigation agents."""

from pydantic import ValidationError

from app.schemas.integrations.strict_json import strict_json
from app.schemas.integrations.virtual_court.investigation import (
    JudgeNextActionResponse,
    ParticipantIntentResponse,
    ParticipantSpeechResponse,
)

from .exceptions import InvestigationInvalidResponseError


RESPONSE_MAX_BYTES = 131072


def _invalid(field, cause=None):
    raise InvestigationInvalidResponseError(
        params={"reason": "schema_validation_failed", "field": field}, cause=cause
    )


def _parse(raw, response_type):
    try:
        data = strict_json(raw, max_bytes=RESPONSE_MAX_BYTES)
        if not isinstance(data, dict):
            _invalid("response")
        response = response_type.model_validate(data)
        if len(response.model_dump_json().encode("utf-8")) > RESPONSE_MAX_BYTES:
            _invalid("response_size")
        return response
    except (ValidationError, ValueError, TypeError, UnicodeError, RecursionError) as exc:
        field = "response"
        if isinstance(exc, ValidationError):
            field = ".".join(map(str, exc.errors()[0]["loc"])) or field
        _invalid(field, exc)


def _references(request, *, participant, kind, topic, evidence, reply):
    context = request.case_context
    topics = {item.topicId for item in context.topics}
    groups = {item.evidenceGroupId: item for item in context.evidenceGroups}
    records = {item.turnId: item for item in request.records}
    if topic is not None and topic not in topics:
        _invalid("topicId")
    if evidence is not None and evidence not in groups:
        _invalid("evidenceGroupId")
    if kind == "present_evidence":
        if evidence is None or groups[evidence].offeringParticipantId != participant:
            _invalid("evidenceGroupId")
    if kind == "examine_evidence":
        if (evidence is None or groups[evidence].offeringParticipantId == participant or
                not any(item.kind == "present_evidence" and item.evidenceGroupId == evidence for item in request.records)):
            _invalid("evidenceGroupId")
    if kind == "respond" and reply not in records:
        _invalid("replyToTurnId")
    if kind != "respond" and reply is not None:
        _invalid("replyToTurnId")


def validate_intent_output(raw, request):
    response = _parse(raw, ParticipantIntentResponse)
    if (response.investigation_id != request.investigation_id or
            response.decision_revision != request.decision_revision):
        _invalid("investigation_id")
    if response.decision == "request":
        _references(request, participant=request.participant_id,
                    kind=response.speech_kind, topic=response.topic_id,
                    evidence=response.evidence_group_id, reply=response.reply_to_turn_id)
        if any(
            item.participantId == request.participant_id and
            item.speechKind == response.speech_kind and
            item.reason.strip() == response.reason.strip() and
            item.topicId == response.topic_id and
            item.evidenceGroupId == response.evidence_group_id and
            item.replyToTurnId == response.reply_to_turn_id
            for item in request.investigation.pendingRequests
        ):
            _invalid("decision")
    return response


def validate_speech_output(raw, request):
    response = _parse(raw, ParticipantSpeechResponse)
    if (response.investigation_id != request.investigation_id or
            response.turn_id != request.turn_id):
        _invalid("turn_id")
    return response


def validate_judge_output(raw, request):
    response = _parse(raw, JudgeNextActionResponse)
    if (response.investigation_id != request.investigation_id or
            response.decision_revision != request.decision_revision):
        _invalid("decision_revision")
    if response.decision == "handoff":
        return response
    action = response.action
    context = request.case_context
    participants = {item.participantId for item in context.participants}
    pending = {item.requestId for item in request.investigation.pendingRequests}
    topics = {item.topicId for item in context.topics}
    groups = {item.evidenceGroupId for item in context.evidenceGroups}
    if action.type in ("grant_request", "reject_request"):
        if action.requestId not in pending:
            _invalid("action.requestId")
    elif action.type == "invite_participant":
        if action.participantId not in participants:
            _invalid("action.participantId")
        _references(request, participant=action.participantId,
                    kind=action.speechKind, topic=action.topicId,
                    evidence=action.evidenceGroupId, reply=action.replyToTurnId)
    elif action.type == "ask_participant":
        if action.participantId not in participants:
            _invalid("action.participantId")
        if action.topicId is not None and action.topicId not in topics:
            _invalid("action.topicId")
        if action.evidenceGroupId is not None and action.evidenceGroupId not in groups:
            _invalid("action.evidenceGroupId")
    elif action.type == "set_context":
        if action.topicId is not None and action.topicId not in topics:
            _invalid("action.topicId")
        if action.evidenceGroupId is not None and action.evidenceGroupId not in groups:
            _invalid("action.evidenceGroupId")
        if (action.topicId == request.investigation.currentTopicId and
                action.evidenceGroupId == request.investigation.currentEvidenceGroupId):
            _invalid("action")
    elif action.type == "close_investigation" and pending:
        _invalid("action")
    return response

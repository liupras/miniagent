"""Validate V4 model decisions and assembled HTTP responses."""

import json
import unicodedata

from pydantic import ValidationError

from app.schemas.integrations.strict_json import strict_json
from app.schemas.integrations.virtual_court.investigation import (
    JudgeNextActionResponse, ParticipantIntentResponse, ParticipantSpeechResponse,
)
from app.schemas.integrations.virtual_court.investigation_model import (
    IntentModelOutput, JudgeModelOutput, SpeechModelOutput,
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


def validate_intent_output(raw, request):
    response = _parse(raw, ParticipantIntentResponse)
    if (response.investigation_id != request.investigation_id or
            response.decision_revision != request.decision_revision):
        _invalid("investigation_id")
    _validate_intent_choice(response, request)
    return response


def _validate_intent_choice(response, request):
    if response.decision == "request":
        topics = {item.topicId for item in request.case_context.topics}
        if response.topic_id not in topics:
            _invalid("topic_id")
        if any(item.participantId == request.participant_id and
               item.speechKind == response.speech_kind and
               item.topicId == response.topic_id and
               _reason_fingerprint(item.reason) ==
               _reason_fingerprint(response.reason or "")
               for item in request.investigation.pendingRequests):
            _invalid("decision")


def _reason_fingerprint(value):
    """Match VirtualCourt's duplicate-request normalization."""
    return "".join(
        character for character in value
        if not character.isspace() and
        not unicodedata.category(character).startswith("P")
    ).lower()


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
    if request.scope is None:
        if "scope" in response.model_fields_set or response.decision == "defer":
            _invalid("scope")
    elif response.scope != request.scope or "scope" not in response.model_fields_set:
        _invalid("scope")
    _validate_judge_choice(response, request)
    return response


def _validate_judge_choice(response, request):
    if response.decision == "defer" and request.scope != "request":
        _invalid("decision")
    if response.decision != "action":
        return
    action = response.action
    allowed = {
        "request": ("grant_request", "reject_request"),
        "next": ("invite_participant",),
        "summary": ("close_investigation",),
    }
    if request.scope is not None and action.type not in allowed[request.scope]:
        _invalid("action.type")
    pending = {item.requestId: item for item in request.investigation.pendingRequests}
    participants = {item.participantId for item in request.case_context.participants}
    topics = {item.topicId for item in request.case_context.topics}
    if action.type in ("grant_request", "reject_request"):
        selected = pending.get(action.requestId)
        if selected is None or selected.locked or request.scope == "request" and action.requestId != request.request_id:
            _invalid("action.requestId")
    elif action.type == "invite_participant":
        if action.participantId not in participants:
            _invalid("action.participantId")
        if request.scope == "next" and action.topicId is None:
            _invalid("action.topicId")
        if action.topicId is not None and action.topicId not in topics:
            _invalid("action.topicId")
    elif action.type == "close_investigation" and pending:
        _invalid("action.type")


def validate_intent_model_output(raw, request):
    """Validate the model's choice, then restore the HTTP binding fields."""
    model = _parse(raw, IntentModelOutput)
    _validate_intent_choice(model, request)
    payload = model.model_dump(mode="json", exclude_unset=True)
    payload["investigation_id"] = request.investigation_id
    payload["decision_revision"] = request.decision_revision
    return validate_intent_output(json.dumps(payload, ensure_ascii=False), request)


def validate_speech_model_output(raw, request):
    model = _parse(raw, SpeechModelOutput)
    payload = {
        "investigation_id": request.investigation_id,
        "turn_id": request.turn_id,
        "speech": model.speech,
    }
    return validate_speech_output(json.dumps(payload, ensure_ascii=False), request)


def validate_judge_model_output(raw, request):
    model = _parse(raw, JudgeModelOutput)
    _validate_judge_choice(model, request)
    payload = model.model_dump(mode="json", exclude_unset=True)
    if model.decision == "action":
        payload["utterance"] = {"mode": "text", "text": model.utterance}
    payload["investigation_id"] = request.investigation_id
    payload["decision_revision"] = request.decision_revision
    if request.scope is not None:
        payload["scope"] = request.scope
    return validate_judge_output(json.dumps(payload, ensure_ascii=False), request)

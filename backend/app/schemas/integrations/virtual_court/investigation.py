"""Contracts for the unified investigation Agent APIs."""

from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

from .judge import StrictModel


Id = Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]
Text = Annotated[str, Field(min_length=1, max_length=8000, pattern=r"\S")]
Reason = Annotated[str, Field(min_length=1, max_length=500, pattern=r"\S")]
Revision = Annotated[int, Field(ge=0)]
SpeechKind = Literal["present_evidence", "examine_evidence", "respond", "supplement"]
TurnKind = Literal["present_evidence", "examine_evidence", "respond", "supplement", "question", "answer", "summary"]


class Participant(StrictModel):
    participantId: Id
    displayName: Id


class Position(StrictModel):
    participantId: Id
    text: Text


class Topic(StrictModel):
    topicId: Id
    text: Text


class EvidenceGroup(StrictModel):
    evidenceGroupId: Id
    offeringParticipantId: Id
    name: Annotated[str, Field(min_length=1, max_length=500)]
    proofPurpose: Text
    materials: list[Text]


class CaseContext(StrictModel):
    summary: Text
    participants: list[Participant] = Field(min_length=2)
    positions: list[Position]
    topics: list[Topic] = Field(min_length=1)
    evidenceGroups: list[EvidenceGroup]

    @model_validator(mode="after")
    def references(self):
        participants = [item.participantId for item in self.participants]
        if len(participants) != len(set(participants)):
            raise ValueError("duplicate participantId")
        for values, label in ((self.topics, "topicId"), (self.evidenceGroups, "evidenceGroupId")):
            ids = [getattr(item, label) for item in values]
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate " + label)
        if any(item.participantId not in participants for item in self.positions):
            raise ValueError("position participant not found")
        if any(item.offeringParticipantId not in participants for item in self.evidenceGroups):
            raise ValueError("evidence offering participant not found")
        return self


class FloorRequest(StrictModel):
    requestId: Id
    participantId: Id
    speechKind: SpeechKind
    reason: Reason
    topicId: Id | None
    evidenceGroupId: Id | None
    replyToTurnId: Id | None


class ActiveTurn(StrictModel):
    turnId: Id
    speakerId: Id
    kind: TurnKind
    taskText: Annotated[str, Field(max_length=8000)]
    topicId: Id | None
    evidenceGroupId: Id | None
    contextEvidenceGroupIds: list[Id]
    replyToTurnId: Id | None
    targetParticipantId: Id | None


class InvestigationState(StrictModel):
    investigationId: Id
    status: Literal["ready", "awaiting_speech", "presenting", "completed"]
    decisionRevision: Revision
    currentTopicId: Id | None
    currentEvidenceGroupIds: list[Id]
    pendingRequests: list[FloorRequest]
    activeTurn: ActiveTurn | None

    @model_validator(mode="after")
    def status_shape(self):
        if (self.status in ("ready", "completed")) != (self.activeTurn is None):
            raise ValueError("investigation status and activeTurn disagree")
        return self


class Record(StrictModel):
    sequence: Annotated[int, Field(ge=1)]
    speakerId: Id
    turnId: Id
    kind: TurnKind
    text: Text
    topicId: Id | None
    evidenceGroupId: Id | None
    contextEvidenceGroupIds: list[Id]


class InvestigationInput(StrictModel):
    investigation_id: Id
    case_context: CaseContext
    investigation: InvestigationState
    records: list[Record] = Field(max_length=512)

    @model_validator(mode="after")
    def consistent(self):
        if self.investigation_id != self.investigation.investigationId:
            raise ValueError("investigation_id mismatch")
        participants = {item.participantId for item in self.case_context.participants}
        topics = {item.topicId for item in self.case_context.topics}
        evidence_order = [item.evidenceGroupId for item in self.case_context.evidenceGroups]
        evidence = set(evidence_order)
        def refs(topic, group):
            if topic is not None and topic not in topics:
                raise ValueError("unknown topicId")
            if group is not None and group not in evidence:
                raise ValueError("unknown evidenceGroupId")
        def focus(ids):
            if len(ids) != len(set(ids)) or any(item not in evidence for item in ids):
                raise ValueError("invalid contextEvidenceGroupIds")
            if ids != [item for item in evidence_order if item in ids]:
                raise ValueError("evidence context must follow case order")
        refs(self.investigation.currentTopicId, None)
        focus(self.investigation.currentEvidenceGroupIds)
        turns = [item.turnId for item in self.records]
        if len(turns) != len(set(turns)):
            raise ValueError("duplicate record turnId")
        sequences = [item.sequence for item in self.records]
        if sequences != sorted(set(sequences)):
            raise ValueError("records must be ordered and unique")
        for item in self.records:
            if item.speakerId != "judge" and item.speakerId not in participants:
                raise ValueError("unknown record speakerId")
            refs(item.topicId, item.evidenceGroupId)
            focus(item.contextEvidenceGroupIds)
            if item.evidenceGroupId is not None and item.evidenceGroupId not in item.contextEvidenceGroupIds:
                raise ValueError("record evidence missing from context")
        for item in self.investigation.pendingRequests:
            if item.participantId not in participants:
                raise ValueError("unknown request participantId")
            refs(item.topicId, item.evidenceGroupId)
            if item.replyToTurnId is not None and item.replyToTurnId not in turns:
                raise ValueError("unknown request replyToTurnId")
        turn = self.investigation.activeTurn
        if turn is not None:
            if turn.speakerId != "judge" and turn.speakerId not in participants:
                raise ValueError("unknown turn speakerId")
            if turn.targetParticipantId is not None and turn.targetParticipantId not in participants:
                raise ValueError("unknown targetParticipantId")
            refs(turn.topicId, turn.evidenceGroupId)
            focus(turn.contextEvidenceGroupIds)
            if turn.evidenceGroupId is not None and turn.evidenceGroupId not in turn.contextEvidenceGroupIds:
                raise ValueError("turn evidence missing from context")
            if turn.replyToTurnId is not None and turn.replyToTurnId not in turns:
                raise ValueError("unknown turn replyToTurnId")
        return self


class ParticipantIntentRequest(InvestigationInput):
    decision_revision: Revision
    participant_id: Id

    @model_validator(mode="after")
    def intent_state(self):
        if self.decision_revision != self.investigation.decisionRevision:
            raise ValueError("decision_revision mismatch")
        if self.participant_id not in {item.participantId for item in self.case_context.participants}:
            raise ValueError("participant_id not found")
        if self.investigation.status == "completed":
            raise ValueError("intent requires active investigation")
        turn = self.investigation.activeTurn
        if turn is not None:
            if turn.kind == "summary":
                raise ValueError("intent is closed after summary submission")
            if turn.speakerId == self.participant_id:
                raise ValueError("current speaker must use speech endpoint")
            if turn.kind == "question" and turn.targetParticipantId == self.participant_id:
                raise ValueError("question target already has a reserved answer turn")
        return self


class ParticipantSpeechRequest(InvestigationInput):
    turn_id: Id
    participant_id: Id

    @model_validator(mode="after")
    def speech_state(self):
        turn = self.investigation.activeTurn
        if self.investigation.status != "awaiting_speech" or turn is None or turn.turnId != self.turn_id or turn.speakerId != self.participant_id:
            raise ValueError("speech requires current participant turn")
        if self.participant_id not in {item.participantId for item in self.case_context.participants}:
            raise ValueError("participant_id not found")
        return self


class JudgeNextActionRequest(InvestigationInput):
    decision_revision: Revision
    scope: Literal["request", "next", "summary"] | None = None
    request_id: Id | None = None

    @model_validator(mode="after")
    def judge_state(self):
        if self.decision_revision != self.investigation.decisionRevision or self.investigation.status != "ready":
            raise ValueError("judge decision requires current ready revision")
        if self.scope is None and "scope" in self.model_fields_set:
            raise ValueError("automatic judge request must omit scope")
        if self.scope == "request":
            if self.request_id is None or self.request_id not in {
                item.requestId for item in self.investigation.pendingRequests
            }:
                raise ValueError("consultation requires selected pending request")
        elif "request_id" in self.model_fields_set:
            raise ValueError("request_id requires request scope")
        if self.scope == "summary" and self.investigation.pendingRequests:
            raise ValueError("summary requires empty pending requests")
        return self


class ParticipantIntentResponse(StrictModel):
    investigation_id: Id
    decision_revision: Revision
    decision: Literal["request", "pass"]
    speech_kind: SpeechKind | None = None
    reason: Reason | None = None
    topic_id: Id | None = None
    evidence_group_id: Id | None = None
    reply_to_turn_id: Id | None = None

    @model_validator(mode="after")
    def decision_shape(self):
        supplied = set(self.model_fields_set)
        optional = {"speech_kind", "reason", "topic_id", "evidence_group_id", "reply_to_turn_id"}
        if self.decision == "request" and not optional <= supplied:
            raise ValueError("request must include all association fields")
        if self.decision == "pass" and supplied & optional:
            raise ValueError("pass cannot include request fields")
        if self.decision == "request" and (self.speech_kind is None or self.reason is None):
            raise ValueError("request requires kind and reason")
        return self


class ParticipantSpeechResponse(StrictModel):
    investigation_id: Id
    turn_id: Id
    speech: Text


class GrantRequest(StrictModel):
    type: Literal["grant_request"]
    requestId: Id


class RejectRequest(StrictModel):
    type: Literal["reject_request"]
    requestId: Id
    reason: Reason


class InviteParticipant(StrictModel):
    type: Literal["invite_participant"]
    participantId: Id
    speechKind: SpeechKind
    taskText: Annotated[str, Field(min_length=1, max_length=1000, pattern=r"\S")]
    topicId: Id | None
    evidenceGroupId: Id | None
    replyToTurnId: Id | None = None


class AskParticipant(StrictModel):
    type: Literal["ask_participant"]
    participantId: Id
    text: Text
    topicId: Id | None


class SetContext(StrictModel):
    type: Literal["set_context"]
    topicId: Id
    evidenceGroupIds: list[Id]

class CloseInvestigation(StrictModel):
    type: Literal["close_investigation"]
    text: Text


JudgeAction = Annotated[Union[GrantRequest, RejectRequest, InviteParticipant, AskParticipant, SetContext, CloseInvestigation], Field(discriminator="type")]


class JudgeNextActionResponse(StrictModel):
    investigation_id: Id
    decision_revision: Revision
    scope: Literal["request", "next", "summary"] | None = None
    decision: Literal["action", "defer", "handoff"]
    action: JudgeAction | None = None
    reason: Reason | None = None

    @model_validator(mode="after")
    def decision_shape(self):
        supplied = set(self.model_fields_set)
        if self.decision == "action" and (self.action is None or "reason" in supplied):
            raise ValueError("action decision requires action only")
        if self.decision == "handoff" and (self.reason is None or "action" in supplied):
            raise ValueError("handoff requires reason only")
        if self.decision == "defer" and (self.scope != "request" or self.reason is None or "action" in supplied):
            raise ValueError("defer requires request scope and reason only")
        return self

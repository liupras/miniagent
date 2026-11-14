"""V4 contracts for investigation intent, speech, and judge decisions."""

from typing import Annotated, Literal, Union
from pydantic import Field, model_validator
from .judge import StrictModel

Id = Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]
Text = Annotated[str, Field(min_length=1, max_length=8000, pattern=r"\S")]
Reason = Annotated[str, Field(max_length=500)]
Revision = Annotated[int, Field(ge=0)]
SpeechKind = Literal["present_evidence", "examine_evidence", "respond", "supplement"]
ScheduledSpeechKind = Literal["present_evidence", "examine_evidence", "respond", "supplement", "answer"]


class Participant(StrictModel):
    participantId: Id
    displayName: Id


class Position(StrictModel):
    participantId: Id
    text: str


class Topic(StrictModel):
    topicId: Id
    text: str


class EvidenceGroup(StrictModel):
    evidenceGroupId: Id
    offeringParticipantId: Id
    name: str
    proofPurpose: str
    materials: list[str]


class CaseContext(StrictModel):
    summary: str
    participants: list[Participant]
    positions: list[Position]
    topics: list[Topic]
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
            raise ValueError("unknown position participant")
        if any(item.offeringParticipantId not in participants for item in self.evidenceGroups):
            raise ValueError("unknown evidence participant")
        return self


class FloorRequest(StrictModel):
    requestId: Id
    participantId: Id
    speechKind: SpeechKind
    topicId: Id
    reason: Reason
    locked: bool


class GrantRequest(StrictModel):
    type: Literal["grant_request"]
    requestId: Id


class RejectRequest(StrictModel):
    type: Literal["reject_request"]
    requestId: Id


class InviteParticipant(StrictModel):
    type: Literal["invite_participant"]
    participantId: Id
    speechKind: ScheduledSpeechKind
    topicId: Id | None = None

    @model_validator(mode="after")
    def optional_topic(self):
        if "topicId" in self.model_fields_set and self.topicId is None:
            raise ValueError("topicId must be text when supplied")
        return self


class CloseInvestigation(StrictModel):
    type: Literal["close_investigation"]


JudgeAction = Annotated[Union[GrantRequest, RejectRequest, InviteParticipant, CloseInvestigation], Field(discriminator="type")]
AnnouncementAction = Annotated[Union[GrantRequest, RejectRequest, InviteParticipant], Field(discriminator="type")]


class AnnouncementTurn(StrictModel):
    turnId: Id
    speakerId: Literal["judge"]
    kind: Literal["announcement"]
    topicId: Id
    plannedAction: AnnouncementAction
    sourceRequestId: Id | None = None


class SummaryTurn(StrictModel):
    turnId: Id
    speakerId: Literal["judge"]
    kind: Literal["summary"]
    plannedAction: CloseInvestigation


class ParticipantTurn(StrictModel):
    turnId: Id
    speakerId: Id
    kind: Literal["participant"]
    speechKind: ScheduledSpeechKind
    topicId: Id
    sourceRequestId: Id | None = None


ActiveTurn = Annotated[Union[AnnouncementTurn, SummaryTurn, ParticipantTurn], Field(discriminator="kind")]


class InvestigationState(StrictModel):
    investigationId: Id
    status: Literal["ready", "awaiting_speech", "presenting"]
    decisionRevision: Revision
    currentTopicId: Id
    displayedEvidenceGroupIds: list[Id]
    pendingRequests: list[FloorRequest]
    activeTurn: ActiveTurn | None

    @model_validator(mode="after")
    def status_shape(self):
        if (self.status == "ready") != (self.activeTurn is None):
            raise ValueError("investigation status and activeTurn disagree")
        return self


class Record(StrictModel):
    sequence: Annotated[int, Field(ge=0)]
    turnId: Id
    speakerId: Id
    kind: Literal["announcement", "summary", "participant"]
    speechKind: ScheduledSpeechKind | None = None
    topicId: Id | None
    text: Text
    sourceRequestId: Id | None

    @model_validator(mode="after")
    def record_shape(self):
        if (self.kind == "participant") != (self.speechKind is not None):
            raise ValueError("record speechKind disagrees with kind")
        if self.kind != "participant" and "speechKind" in self.model_fields_set:
            raise ValueError("judge record cannot contain speechKind")
        return self


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
        evidence = {item.evidenceGroupId for item in self.case_context.evidenceGroups}
        if self.investigation.currentTopicId not in topics:
            raise ValueError("unknown currentTopicId")
        ids = self.investigation.displayedEvidenceGroupIds
        if len(ids) != len(set(ids)) or any(item not in evidence for item in ids):
            raise ValueError("invalid displayedEvidenceGroupIds")
        request_ids = [item.requestId for item in self.investigation.pendingRequests]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("duplicate requestId")
        for item in self.investigation.pendingRequests:
            if item.participantId not in participants or item.topicId not in topics:
                raise ValueError("invalid pending request reference")
        sequences = [item.sequence for item in self.records]
        if sequences != sorted(set(sequences)):
            raise ValueError("records must be ordered and unique")
        for item in self.records:
            if item.speakerId != "judge" and item.speakerId not in participants:
                raise ValueError("unknown record speakerId")
            if item.topicId is not None and item.topicId not in topics:
                raise ValueError("unknown record topicId")
            if item.kind == "participant" and item.topicId is None:
                raise ValueError("participant record requires topicId")
        turn = self.investigation.activeTurn
        if turn is not None:
            if turn.kind == "participant" and (turn.speakerId not in participants or turn.topicId not in topics):
                raise ValueError("invalid participant turn")
            if turn.kind == "announcement" and turn.topicId not in topics:
                raise ValueError("invalid announcement topicId")
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
        turn = self.investigation.activeTurn
        if turn is not None and (turn.kind == "summary" or turn.speakerId == self.participant_id or
                                 turn.kind == "announcement" and (
                                     turn.plannedAction.type == "invite_participant" and
                                     turn.plannedAction.participantId == self.participant_id or
                                     turn.plannedAction.type == "grant_request" and
                                     any(item.requestId == turn.plannedAction.requestId and
                                         item.participantId == self.participant_id
                                         for item in self.investigation.pendingRequests))):
            raise ValueError("intent is not available for the current speaker")
        return self


class ParticipantSpeechRequest(InvestigationInput):
    turn_id: Id
    participant_id: Id

    @model_validator(mode="after")
    def speech_state(self):
        turn = self.investigation.activeTurn
        if (self.investigation.status != "awaiting_speech" or turn is None or
                turn.kind != "participant" or turn.turnId != self.turn_id or
                turn.speakerId != self.participant_id):
            raise ValueError("speech requires current participant turn")
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
    topic_id: Id | None = None
    reason: Reason | None = None

    @model_validator(mode="after")
    def decision_shape(self):
        supplied = set(self.model_fields_set)
        if self.decision == "request":
            if self.speech_kind is None or self.topic_id is None:
                raise ValueError("request requires speech_kind and topic_id")
            if "reason" in supplied and self.reason is None:
                raise ValueError("reason must be text when supplied")
        elif supplied & {"speech_kind", "topic_id", "reason"}:
            raise ValueError("pass cannot include request fields")
        return self


class ParticipantSpeechResponse(StrictModel):
    investigation_id: Id
    turn_id: Id
    speech: Text


class TextUtterance(StrictModel):
    mode: Literal["text"]
    text: Annotated[str, Field(max_length=8000)] | None = None

    @model_validator(mode="after")
    def text_shape(self):
        if "text" in self.model_fields_set and self.text is None:
            raise ValueError("utterance text must be text when supplied")
        return self


class JudgeNextActionResponse(StrictModel):
    investigation_id: Id
    decision_revision: Revision
    scope: Literal["request", "next", "summary"] | None = None
    decision: Literal["action", "defer", "handoff"]
    action: JudgeAction | None = None
    utterance: TextUtterance | None = None
    reason: Text | None = None

    @model_validator(mode="after")
    def decision_shape(self):
        supplied = set(self.model_fields_set)
        if self.decision == "action":
            if self.action is None or self.utterance is None or "reason" in supplied:
                raise ValueError("action requires action and utterance only")
            if self.action.type == "close_investigation" and not (self.utterance.text or "").strip():
                raise ValueError("summary requires spoken text")
        elif self.action is not None or self.utterance is not None or "action" in supplied or "utterance" in supplied:
            raise ValueError("defer and handoff require reason only")
        if self.decision == "handoff" and self.reason is None:
            raise ValueError("handoff requires reason")
        if self.decision == "defer" and (self.scope != "request" or self.reason is None):
            raise ValueError("defer requires request scope and reason")
        return self

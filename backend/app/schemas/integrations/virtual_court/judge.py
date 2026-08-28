"""V1 contract for VirtualCourt judge decisions."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from .common import (
    CaseContext,
    CourtEvent,
    EvidenceContext,
    IntegrationModel,
    PartyRole,
    StageSummary,
)


class TriggerType(StrEnum):
    LEGAL_QUESTION = "LEGAL_QUESTION"
    CLARIFICATION_NEEDED = "CLARIFICATION_NEEDED"
    SUPPLEMENTARY_QUESTION_NEEDED = "SUPPLEMENTARY_QUESTION_NEEDED"
    OFF_TOPIC_OR_VERBOSE = "OFF_TOPIC_OR_VERBOSE"
    SUMMARY_REQUESTED = "SUMMARY_REQUESTED"
    STAGE_READY = "STAGE_READY"
    MANUAL_ASSIST = "MANUAL_ASSIST"


class ActionType(StrEnum):
    NO_ACTION = "NO_ACTION"
    ASK_PARTY = "ASK_PARTY"
    REQUEST_CLARIFICATION = "REQUEST_CLARIFICATION"
    SUMMARIZE = "SUMMARIZE"
    PAUSE_SESSION = "PAUSE_SESSION"
    RESUME_SESSION = "RESUME_SESSION"
    END_CURRENT_SPEECH = "END_CURRENT_SPEECH"
    END_CURRENT_STAGE = "END_CURRENT_STAGE"
    ADVANCE_STEP = "ADVANCE_STEP"
    ADJOURN = "ADJOURN"


class SpeechType(StrEnum):
    NONE = "NONE"
    QUESTION = "QUESTION"
    CLARIFICATION = "CLARIFICATION"
    SUMMARY = "SUMMARY"
    LEGAL_EXPLANATION = "LEGAL_EXPLANATION"
    PROCEDURAL_DIRECTION = "PROCEDURAL_DIRECTION"


class ConfidenceLevel(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"


class JudgeDecisionRequest(IntegrationModel):
    current_stage: str = Field(min_length=1, max_length=64)
    current_step: str = Field(
        min_length=2,
        max_length=64,
        pattern=r"^[A-Z][A-Z0-9-]+$",
    )
    trigger: TriggerType
    task: str = Field(min_length=1, max_length=2000)
    current_speaker: PartyRole | None = None
    allowed_actions: list[ActionType] = Field(default_factory=list, max_length=10)
    allowed_targets: list[PartyRole] = Field(default_factory=list, max_length=2)
    case_context: CaseContext
    current_evidence: EvidenceContext | None = None
    stage_summaries: list[StageSummary] = Field(default_factory=list, max_length=12)
    recent_events: list[CourtEvent] = Field(default_factory=list, max_length=30)

    @field_validator("allowed_actions")
    @classmethod
    def allowed_actions_must_be_unique(
        cls,
        value: list[ActionType],
    ) -> list[ActionType]:
        if len(value) != len(set(value)):
            raise ValueError("allowed_actions must not contain duplicates")
        return value

    @field_validator("allowed_targets")
    @classmethod
    def allowed_targets_must_be_unique(
        cls,
        value: list[PartyRole],
    ) -> list[PartyRole]:
        if len(value) != len(set(value)):
            raise ValueError("allowed_targets must not contain duplicates")
        return value

    @model_validator(mode="after")
    def actions_requiring_a_party_must_have_targets(self):
        party_actions = {
            ActionType.ASK_PARTY,
            ActionType.REQUEST_CLARIFICATION,
        }
        if party_actions.intersection(self.allowed_actions) and not self.allowed_targets:
            raise ValueError(
                "allowed_targets is required when a party-directed action is allowed"
            )
        return self


class JudgeSpeech(IntegrationModel):
    type: SpeechType
    text: str = Field(default="", max_length=4000)
    target_role: PartyRole | None = None

    @model_validator(mode="after")
    def validate_text_and_target(self):
        targeted_types = {SpeechType.QUESTION, SpeechType.CLARIFICATION}
        if self.type == SpeechType.NONE and self.text:
            raise ValueError("speech text must be empty when type is NONE")
        if self.type != SpeechType.NONE and not self.text:
            raise ValueError("speech text is required unless type is NONE")
        if self.type in targeted_types and self.target_role is None:
            raise ValueError("target_role is required for question or clarification")
        if self.type not in targeted_types and self.target_role is not None:
            raise ValueError("target_role is only valid for question or clarification")
        return self


class JudgeActionProposal(IntegrationModel):
    type: ActionType
    target_role: PartyRole | None = None

    @model_validator(mode="after")
    def validate_target(self):
        targeted_actions = {
            ActionType.ASK_PARTY,
            ActionType.REQUEST_CLARIFICATION,
        }
        if self.type in targeted_actions and self.target_role is None:
            raise ValueError("target_role is required for a party-directed action")
        if self.type not in targeted_actions and self.target_role is not None:
            raise ValueError("target_role is only valid for a party-directed action")
        return self


class LegalCitation(IntegrationModel):
    source: str = Field(min_length=1, max_length=512)
    article_no: str = Field(default="", max_length=64)
    excerpt: str | None = Field(default=None, max_length=2000)


class JudgeDecisionResponse(IntegrationModel):
    speech: JudgeSpeech
    action: JudgeActionProposal
    legal_citations: list[LegalCitation] = Field(default_factory=list, max_length=20)
    confidence: ConfidenceLevel
    requires_human_review: bool = False
    warnings: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_decision_consistency(self):
        if (
            self.action.target_role is not None
            and self.speech.target_role is not None
            and self.action.target_role != self.speech.target_role
        ):
            raise ValueError("speech and action must target the same party")

        if (
            self.speech.type == SpeechType.LEGAL_EXPLANATION
            and not self.legal_citations
            and self.confidence != ConfidenceLevel.INSUFFICIENT
        ):
            raise ValueError(
                "a legal explanation without citations must have INSUFFICIENT confidence"
            )
        if self.confidence == ConfidenceLevel.INSUFFICIENT and not self.warnings:
            raise ValueError("INSUFFICIENT confidence requires at least one warning")

        expected_speech_types = {
            ActionType.ASK_PARTY: SpeechType.QUESTION,
            ActionType.REQUEST_CLARIFICATION: SpeechType.CLARIFICATION,
            ActionType.SUMMARIZE: SpeechType.SUMMARY,
        }
        expected_speech_type = expected_speech_types.get(self.action.type)
        if expected_speech_type is not None and self.speech.type != expected_speech_type:
            raise ValueError(
                f"{self.action.type} requires {expected_speech_type} speech"
            )
        return self

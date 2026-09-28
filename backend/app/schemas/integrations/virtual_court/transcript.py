"""TranscriptAPI V3 contracts using VirtualCourt domain names."""

from typing import Literal

from pydantic import Field, model_validator

from .judge import (
    CONTENT_MAX_CODEPOINTS,
    StrictModel,
    Version,
    content_size,
    text_type,
)


TRANSCRIPT_MAX_CODEPOINTS = 64000
TRANSCRIPT_RESPONSE_MAX_BYTES = 524288
TranscriptRole = Literal["judge", "clerk", "plaintiff", "defendant", "system"]
TranscriptPhase = Literal[
    "waiting",
    "court_discipline",
    "court_opening",
    "identity_verification",
    "rights_and_recusal",
    "claims_and_defence",
    "court_investigation",
    "evidence_presentation",
    "final_statements",
    "adjournment",
]


class TranscriptCaseInfo(StrictModel):
    case_id: text_type(256)
    case_number: text_type(256)
    court_name: text_type(256)
    procedure: text_type(512)
    cause_of_action: text_type(512)
    subject_matter: text_type(1000)
    is_simulated: bool
    legal_effect_disclaimer: str = Field(max_length=1000)


class TranscriptParticipant(StrictModel):
    participant_id: text_type(128)
    role: TranscriptRole
    display_name: text_type(256)
    description: str = Field(max_length=512)


class TranscriptRecord(StrictModel):
    sequence: int = Field(ge=1, le=9223372036854775807)
    step_id: text_type(128)
    phase: TranscriptPhase
    role: TranscriptRole
    text: text_type(8000)
    is_intervention: bool


class TranscriptOrganizedRecord(StrictModel):
    sequence: int = Field(ge=1, le=9223372036854775807)
    text: text_type(8000)


class TranscriptGenerateRequestV3(StrictModel):
    """Authoritative VirtualCourt metadata plus complete committed speeches."""

    state_version: Version
    case_info: TranscriptCaseInfo
    participants: list[TranscriptParticipant] = Field(max_length=32)
    records: list[TranscriptRecord] = Field(max_length=512)

    @model_validator(mode="after")
    def shape_and_content_budget(self):
        participant_ids = [item.participant_id for item in self.participants]
        if len(participant_ids) != len(set(participant_ids)):
            raise ValueError("duplicate participant_id")
        sequences = [record.sequence for record in self.records]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise ValueError("record sequence must be strictly increasing")
        size = content_size(self.case_info.model_dump())
        size += sum(content_size(item.model_dump()) for item in self.participants)
        size += sum(content_size(record.model_dump()) for record in self.records)
        if size > CONTENT_MAX_CODEPOINTS:
            raise ValueError("content_budget exceeded")
        return self


class TranscriptGenerateResponseV3(StrictModel):
    """One organized text result for every authoritative input record."""

    state_version: Version
    records: list[TranscriptOrganizedRecord] = Field(max_length=512)

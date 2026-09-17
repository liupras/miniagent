"""Frozen TranscriptAPI V2 request and response contracts."""

from pydantic import Field, model_validator

from .judge import (
    CONTENT_MAX_CODEPOINTS,
    JudgeCaseContext,
    JudgeRecord,
    StrictModel,
    Version,
    content_size,
    text_type,
)


TRANSCRIPT_MAX_CODEPOINTS = 64000
TRANSCRIPT_RESPONSE_MAX_BYTES = 524288


class TranscriptGenerateRequestV2(StrictModel):
    """Complete court material required to generate one transcript draft."""

    state_version: Version
    case_context: JudgeCaseContext
    records: list[JudgeRecord] = Field(max_length=512)

    @model_validator(mode="after")
    def content_budget(self):
        size = content_size(self.case_context.model_dump())
        size += sum(content_size(record.model_dump()) for record in self.records)
        if size > CONTENT_MAX_CODEPOINTS:
            raise ValueError("content_budget exceeded")
        return self


class TranscriptGenerateResponseV2(StrictModel):
    """A transcript draft bound to the caller's trusted state version."""

    state_version: Version
    transcript: text_type(TRANSCRIPT_MAX_CODEPOINTS)

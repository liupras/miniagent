"""Frozen Party Reply API V1 contract."""

from typing import Annotated

from pydantic import Field, model_validator

from .common import PartyRole
from .judge import (
    CONTENT_MAX_CODEPOINTS,
    RESPONSE_MAX_BYTES,
    JudgeCaseContext,
    JudgeRecord,
    StrictModel,
    Version,
    _enum_string,
    content_size,
)


Party = Annotated[PartyRole, _enum_string(PartyRole)]
QUESTION_MAX_CODEPOINTS = 1000
RESPONSE_SPEECH_MAX_CODEPOINTS = 1000


class PartyReplyRequestV1(StrictModel):
    state_version: Version
    role: Party
    question: Annotated[
        str,
        Field(min_length=1, max_length=QUESTION_MAX_CODEPOINTS, pattern=r"\S"),
    ]
    case_context: JudgeCaseContext
    records: list[JudgeRecord] = Field(max_length=512)

    @model_validator(mode="after")
    def content_budget(self):
        size = len(self.question)
        size += content_size(self.case_context.model_dump(exclude_unset=True))
        size += sum(content_size(record.model_dump()) for record in self.records)
        if size > CONTENT_MAX_CODEPOINTS:
            raise ValueError("content_budget exceeded")
        return self


class PartyReplyResponseV1(StrictModel):
    state_version: Version
    speech: Annotated[
        str,
        Field(
            min_length=1,
            max_length=RESPONSE_SPEECH_MAX_CODEPOINTS,
            pattern=r"\S",
        ),
    ]


PARTY_REPLY_RESPONSE_MAX_BYTES = RESPONSE_MAX_BYTES

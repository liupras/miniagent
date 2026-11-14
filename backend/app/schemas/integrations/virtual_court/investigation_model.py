"""Strict model-only outputs for the V4 investigation agents.

Room binding fields belong to the HTTP request and are never model outputs.
"""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .investigation import Id, JudgeAction, Reason, SpeechKind, Text
from .judge import StrictModel


class IntentModelOutput(StrictModel):
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


class SpeechModelOutput(StrictModel):
    speech: Text


class JudgeModelOutput(StrictModel):
    decision: Literal["action", "defer", "handoff"]
    action: JudgeAction | None = None
    utterance: Annotated[str, Field(max_length=8000)] | None = None
    reason: Text | None = None

    @model_validator(mode="after")
    def decision_shape(self):
        supplied = set(self.model_fields_set)
        if self.decision == "action":
            if (self.action is None or self.utterance is None or
                    "reason" in supplied):
                raise ValueError("action requires action and utterance only")
            if self.action.type == "close_investigation" and not self.utterance.strip():
                raise ValueError("summary requires spoken text")
        elif (self.reason is None or
              supplied & {"action", "utterance"}):
            raise ValueError("defer and handoff require reason only")
        return self

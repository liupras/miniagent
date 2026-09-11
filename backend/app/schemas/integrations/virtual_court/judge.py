"""Frozen JudgeAPI V2 contract. Lengths are Unicode code points, not UTF-16 units."""
import json
from enum import StrEnum
from typing import Annotated
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

REQUEST_MAX_BYTES = 524288
RESPONSE_MAX_BYTES = 131072
CONTENT_MAX_CODEPOINTS = 64000
class JudgePhase(StrEnum):
    INVESTIGATION = 'INVESTIGATION'
    DEBATE = 'DEBATE'

class JudgeDecision(StrEnum):
    ASK = 'ASK'
    CONTINUE = 'CONTINUE'
    COMPLETE = 'COMPLETE'
    HANDOFF = 'HANDOFF'
    EXPLAIN_LAW = 'EXPLAIN_LAW'
    NO_ACTION = 'NO_ACTION'

class JudgeRecordType(StrEnum):
    SPEECH = 'SPEECH'
    SUMMARY = 'SUMMARY'

def _enum_string(enum_type):
    """Accept exact wire strings without weakening the model's strict validation."""
    def parse(value):
        if isinstance(value, enum_type):
            return value
        if type(value) is str:
            return enum_type(value)
        raise ValueError('expected a protocol string or matching enum member')
    return BeforeValidator(parse)

Phase = Annotated[JudgePhase, _enum_string(JudgePhase)]
Decision = Annotated[JudgeDecision, _enum_string(JudgeDecision)]
RecordType = Annotated[JudgeRecordType, _enum_string(JudgeRecordType)]

PHASE_DECISIONS = {
    JudgePhase.INVESTIGATION: frozenset((JudgeDecision.ASK, JudgeDecision.COMPLETE,
        JudgeDecision.HANDOFF, JudgeDecision.EXPLAIN_LAW, JudgeDecision.NO_ACTION)),
    JudgePhase.DEBATE: frozenset((JudgeDecision.CONTINUE, JudgeDecision.COMPLETE,
        JudgeDecision.HANDOFF, JudgeDecision.EXPLAIN_LAW, JudgeDecision.NO_ACTION)),
}

def text_type(limit):
    return Annotated[str, Field(min_length=1, max_length=limit, pattern=r'\S')]
Role = text_type(64)
Version = Annotated[int, Field(ge=0, le=9223372036854775807)]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class JudgeCaseContext(StrictModel):
    summary: text_type(16000)
    claims: list[text_type(4000)] = Field(max_length=30)
    defenses: list[text_type(4000)] = Field(max_length=30)
    dispute_focuses: list[text_type(1000)] = Field(max_length=20)
    # Omission is valid only for investigation; explicit null is never valid.
    investigation_summary: text_type(16000) = None

class JudgeIssue(StrictModel):
    id: text_type(64)
    question: text_type(1000)

class JudgeRecord(StrictModel):
    type: RecordType
    role: Role | None
    text: text_type(16000)

    @model_validator(mode='after')
    def shape(self):
        if self.type == JudgeRecordType.SPEECH and (self.role is None or len(self.text) > 8000):
            raise ValueError('SPEECH requires a role and at most 8000 code points')
        if self.type == JudgeRecordType.SUMMARY and self.role is not None:
            raise ValueError('SUMMARY role must be null')
        return self

def content_size(value):
    if isinstance(value, str): return len(value)
    if isinstance(value, dict): return sum(content_size(v) for v in value.values())
    if isinstance(value, list): return sum(content_size(v) for v in value)
    return 0

class JudgeDecisionRequest(StrictModel):
    state_version: Version
    phase: Phase
    allowed_decisions: list[Decision] = Field(min_length=1, max_length=5)
    allowed_targets: list[Role] = Field(max_length=32)
    case_context: JudgeCaseContext
    current_issue: JudgeIssue | None
    records: list[JudgeRecord] = Field(max_length=512)

    @model_validator(mode='after')
    def permissions_and_context(self):
        decisions = set(self.allowed_decisions)
        if len(decisions) != len(self.allowed_decisions) or not decisions <= PHASE_DECISIONS[self.phase]:
            raise ValueError('invalid or duplicate decisions for phase')
        if JudgeDecision.NO_ACTION in decisions and decisions != {JudgeDecision.EXPLAIN_LAW, JudgeDecision.NO_ACTION, JudgeDecision.HANDOFF}:
            raise ValueError('NO_ACTION requires exactly the law-check decision set')
        if JudgeDecision.HANDOFF not in decisions:
            raise ValueError('HANDOFF must be allowed')
        if len(set(self.allowed_targets)) != len(self.allowed_targets):
            raise ValueError('duplicate targets')
        if JudgeDecision.ASK in decisions and not self.allowed_targets:
            raise ValueError('ASK requires allowed_targets')
        has_summary = 'investigation_summary' in self.case_context.model_fields_set
        if self.phase == JudgePhase.INVESTIGATION:
            if self.current_issue is not None or has_summary:
                raise ValueError('investigation cannot include current_issue or investigation_summary')
        elif self.current_issue is None or not has_summary:
            raise ValueError('debate requires current_issue and investigation_summary')
        size = content_size(self.case_context.model_dump(exclude_unset=True))
        size += sum(content_size(r.model_dump()) for r in self.records)
        size += len(self.current_issue.question) if self.current_issue else 0
        if size > CONTENT_MAX_CODEPOINTS:
            raise ValueError('content_budget exceeded')
        return self

class JudgeAgentOutput(StrictModel):
    decision: Decision
    target: Role | None
    speech: Annotated[str, Field(max_length=4000)]
    pending_points: list[text_type(1000)] = Field(max_length=30)

    @model_validator(mode='after')
    def shape(self):
        if self.decision == JudgeDecision.NO_ACTION:
            if self.speech != '' or self.pending_points:
                raise ValueError('NO_ACTION requires empty speech and pending_points')
        elif not self.speech.strip():
            raise ValueError('speech must be nonblank')
        if (self.target is not None) != (self.decision == JudgeDecision.ASK):
            raise ValueError('only ASK requires target; other targets must be null')
        if self.decision in (JudgeDecision.CONTINUE, JudgeDecision.HANDOFF) and not self.pending_points:
            raise ValueError('CONTINUE and HANDOFF require pending_points')
        return self

class JudgeDecisionResponse(JudgeAgentOutput):
    state_version: Version

def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError('duplicate JSON field')
            result[key] = value
        return result
    def invalid_constant(_): raise ValueError('invalid JSON constant')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)

def judge_agent_output_json_schema():
    return JudgeAgentOutput.model_json_schema()

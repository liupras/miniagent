"""Frozen JudgeAPI V2 contract. Lengths are Unicode code points, not UTF-16 units."""
import json
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

REQUEST_MAX_BYTES = 524288
RESPONSE_MAX_BYTES = 131072
CONTENT_MAX_CODEPOINTS = 64000
PHASE_DECISIONS = {
    'INVESTIGATION': frozenset(('ASK', 'COMPLETE', 'HANDOFF', 'EXPLAIN_LAW', 'NO_ACTION')),
    'DEBATE': frozenset(('CONTINUE', 'COMPLETE', 'HANDOFF', 'EXPLAIN_LAW', 'NO_ACTION')),
}
Phase = Literal['INVESTIGATION', 'DEBATE']
Decision = Literal['ASK', 'CONTINUE', 'COMPLETE', 'HANDOFF', 'EXPLAIN_LAW', 'NO_ACTION']
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
    type: Literal['SPEECH', 'SUMMARY']
    role: Role | None
    text: text_type(16000)

    @model_validator(mode='after')
    def shape(self):
        if self.type == 'SPEECH' and (self.role is None or len(self.text) > 8000):
            raise ValueError('SPEECH requires a role and at most 8000 code points')
        if self.type == 'SUMMARY' and self.role is not None:
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
        if 'NO_ACTION' in decisions and decisions != {'EXPLAIN_LAW', 'NO_ACTION', 'HANDOFF'}:
            raise ValueError('NO_ACTION requires exactly the law-check decision set')
        if 'HANDOFF' not in decisions:
            raise ValueError('HANDOFF must be allowed')
        if len(set(self.allowed_targets)) != len(self.allowed_targets):
            raise ValueError('duplicate targets')
        if 'ASK' in decisions and not self.allowed_targets:
            raise ValueError('ASK requires allowed_targets')
        has_summary = 'investigation_summary' in self.case_context.model_fields_set
        if self.phase == 'INVESTIGATION':
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
        if self.decision == 'NO_ACTION':
            if self.speech != '' or self.pending_points:
                raise ValueError('NO_ACTION requires empty speech and pending_points')
        elif not self.speech.strip():
            raise ValueError('speech must be nonblank')
        if (self.target is not None) != (self.decision == 'ASK'):
            raise ValueError('only ASK requires target; other targets must be null')
        if self.decision in ('CONTINUE', 'HANDOFF') and not self.pending_points:
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

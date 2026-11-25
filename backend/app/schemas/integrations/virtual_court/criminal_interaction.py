"""Criminal interaction HTTP contract. Case and room bindings stay outside model output."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import Field, model_validator

from .judge import StrictModel


Operation = Literal["intent", "participant_speech", "witness_speech", "judge_action"]
Role = Literal["judge", "prosecutor", "defense_counsel", "accused", "witness"]
Id = str
PARTY_ROLES = {"prosecutor", "defense_counsel", "accused"}
MODE_PARTY_ROLES = {
    "criminal_investigation": PARTY_ROLES,
    "criminal_debate": {"prosecutor", "defense_counsel"},
}
SPEECH_KINDS = {
    "criminal_investigation": {
        "question_accused", "question_witness", "present_evidence",
        "examine_evidence", "statement",
    },
    "criminal_debate": {"debate_statement", "rebuttal"},
}


@lru_cache(maxsize=2)
def _schema(name: str) -> Draft202012Validator:
    path = Path(__file__).parent / "contracts" / name
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))


class CriminalInteractionRequest(StrictModel):
    contractVersion: Literal["criminal-ai-v1"]
    operation: Operation
    callId: Id
    roomEpoch: Id
    stepId: Id
    stepRunId: Id
    sourceStateVersion: int = Field(ge=0)
    caseRevisionId: Id
    caseContentSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    procedureVersionId: Literal["criminal-first-instance-v1"]
    procedureSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    targetParticipantId: Id
    targetRoleId: Role
    casePackage: dict[str, Any]
    interaction: dict[str, Any]
    records: list[dict[str, Any]] = Field(max_length=512)

    @model_validator(mode="after")
    def consistent(self):
        for name, value in (("criminal-ai-request-v1.schema.json",
                             self.model_dump(mode="json")),
                            ("criminal-case-v1.schema.json", self.casePackage)):
            error = next(_schema(name).iter_errors(value), None)
            if error is not None:
                raise ValueError(f"{name}: {error.json_path}: {error.message}")
        if any(not value or len(value) > 128 for value in (
            self.callId, self.roomEpoch, self.stepId, self.stepRunId,
            self.caseRevisionId, self.targetParticipantId,
        )):
            raise ValueError("missing or oversized binding ID")
        case = self.casePackage
        if (case.get("contractVersion") != "1.0" or
                case.get("frozenRequirementsVersion") != "CRIMINAL-V1" or
                not isinstance(case.get("caseInfo"), dict) or
                not case["caseInfo"].get("isSimulated")):
            raise ValueError("invalid criminal case package")
        if any(item["reviewStatus"] != "approved" for key in
               ("witnessProfiles", "legalSources", "segmentContents")
               for item in case[key]):
            raise ValueError("case package is not approved")
        people = case.get("participants")
        if not isinstance(people, list) or any(not isinstance(p, dict) for p in people):
            raise ValueError("invalid participants")
        by_id = {p.get("participantId"): p.get("role") for p in people}
        if (len(by_id) != len(people) or
                by_id.get(self.targetParticipantId) != self.targetRoleId):
            raise ValueError("target participant and role disagree")
        state = self.interaction
        mode = state.get("mode")
        if (mode not in SPEECH_KINDS or state.get("status") not in
                {"ready", "awaiting_speech", "presenting"} or
                not state.get("investigationId") or
                not isinstance(state.get("decisionRevision"), int) or
                state["decisionRevision"] < 0 or
                not isinstance(state.get("roundIndex"), int) or
                state["roundIndex"] < 0):
            raise ValueError("invalid interaction state")
        turn = state.get("activeTurn")
        if self.operation == "judge_action":
            if (self.targetRoleId != "judge" or state["status"] != "ready" or
                    turn is not None):
                raise ValueError("judge requires a ready floor")
        elif self.operation == "intent":
            if (self.targetRoleId not in MODE_PARTY_ROLES[mode] or
                    (isinstance(turn, dict) and
                     (turn.get("kind") == "summary" or
                      turn.get("speakerId") == self.targetParticipantId))):
                raise ValueError("intent requires an eligible party")
        else:
            expected = "witness" if self.operation == "witness_speech" else None
            if ((expected is not None and self.targetRoleId != expected) or
                    (expected is None and self.targetRoleId not in
                     MODE_PARTY_ROLES[mode])):
                raise ValueError("speech role mismatch")
            if (self.operation == "witness_speech" and
                    mode != "criminal_investigation"):
                raise ValueError("witness can only speak in investigation")
            if (self.operation == "witness_speech" and
                    sum(item["participantId"] == self.targetParticipantId for item in
                        case["witnessProfiles"]) != 1):
                raise ValueError("witness profile missing")
            if (state["status"] != "awaiting_speech" or
                    not isinstance(turn, dict) or turn.get("kind") != "participant" or
                    turn.get("speakerId") != self.targetParticipantId or
                    not turn.get("turnId")):
                raise ValueError("speech requires the current turn")
        sequences = [r.get("sequence") for r in self.records]
        if (any(not isinstance(n, int) or n < 1 for n in sequences) or
                sequences != sorted(set(sequences)) or
                any(by_id.get(r.get("participantId")) != r.get("roleId")
                    for r in self.records)):
            raise ValueError("invalid courtroom records")
        return self


class CriminalInteractionResponse(StrictModel):
    contractVersion: Literal["criminal-ai-v1"]
    operation: Operation
    callId: Id
    roomEpoch: Id
    stepRunId: Id
    sourceStateVersion: int
    investigationId: Id
    decisionRevision: int
    turnId: str | None = None
    result: dict[str, Any]

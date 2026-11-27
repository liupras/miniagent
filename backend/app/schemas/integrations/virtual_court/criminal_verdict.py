"""Frozen criminal-verdict-v1 transport contract."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import Field, model_validator

from .judge import StrictModel


@lru_cache(maxsize=2)
def _schema(name: str) -> Draft202012Validator:
    path = Path(__file__).parent / "contracts" / name
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))


class CriminalVerdictRequest(StrictModel):
    contractVersion: Literal["criminal-verdict-v1"]
    decisionRunId: str
    roomEpoch: str
    stepRunId: str
    caseRevisionId: str
    caseContentSha256: str
    procedureVersionId: str = Field(min_length=1, max_length=128)
    procedureSha256: str
    sourceStateVersion: int = Field(ge=0)
    basisSha256: str
    basis: dict[str, Any]

    @model_validator(mode="after")
    def valid_contract(self):
        error = next(_schema("criminal-verdict-request-v1.schema.json")
                     .iter_errors(self.model_dump(mode="json")), None)
        if error is not None:
            raise ValueError(f"verdict request {error.json_path}: {error.message}")
        basis = self.basis
        records = basis["records"]
        sequences = [row["sequence"] for row in records]
        if sequences != sorted(set(sequences)):
            raise ValueError("verdict records must be ordered and unique")
        last = next((row for row in records if row["sequence"] ==
                     basis["lastStatementSequence"]), None)
        if last is None or last["roleId"] != "accused":
            raise ValueError("the accused's final statement is missing")
        participant_roles = {row["participantId"]: row["roleId"]
                             for row in basis["participants"]}
        if len(participant_roles) != len(basis["participants"]) or any(
                participant_roles.get(row["participantId"]) != row["roleId"]
                for row in records):
            raise ValueError("verdict record participant mismatch")
        material_ids = {row["materialId"] for row in basis["evidenceMaterials"]}
        if len(material_ids) != len(basis["evidenceMaterials"]) or any(
                set(row["evidenceMaterialIds"]) - material_ids for row in records):
            raise ValueError("verdict evidence reference mismatch")
        for material in basis["evidenceMaterials"]:
            if set(material["speechSequences"]) - set(sequences):
                raise ValueError("verdict evidence speech reference mismatch")
        for key, id_key in (("charges", "chargeId"),
                            ("disputeFocuses", "focusId"),
                            ("legalSources", "legalSourceId")):
            values = [row[id_key] for row in basis[key]]
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {id_key}")
        legal_ids = {row["legalSourceId"] for row in basis["legalSources"]}
        if any(set(row["legalSourceIds"]) - legal_ids
               for row in basis["charges"]):
            raise ValueError("charge legal source mismatch")
        return self


class CriminalVerdictResponse(StrictModel):
    contractVersion: Literal["criminal-verdict-v1"]
    decisionRunId: str
    roomEpoch: str
    stepRunId: str
    sourceStateVersion: int
    basisSha256: str
    status: Literal["decision", "handoff"]
    decision: dict[str, Any] | None = None
    handoffReason: str | None = None

    @model_validator(mode="after")
    def valid_contract(self):
        error = next(_schema("criminal-verdict-response-v1.schema.json")
                     .iter_errors(self.model_dump(mode="json", exclude_none=True)), None)
        if error is not None:
            raise ValueError(f"verdict response {error.json_path}: {error.message}")
        return self

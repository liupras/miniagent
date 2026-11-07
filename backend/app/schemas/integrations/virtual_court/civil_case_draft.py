"""Civil case draft generation V2: uploaded document text in, reviewable semantics out."""

from typing import Literal

from pydantic import Field, model_validator

from .judge import StrictModel, text_type


CIVIL_DRAFT_RESPONSE_MAX_BYTES = 524288


Side = Literal["plaintiff", "defendant"]
EntityType = Literal["natural_person", "legal_entity"]
ClaimCategory = Literal[
    "cease_infringement", "public_apology", "monetary_compensation", "litigation_costs"
]


class CivilSourceDocumentV2(StrictModel):
    name: text_type(256)
    text: text_type(60000)


class CivilSegmentRequirementV2(StrictModel):
    name: text_type(256)
    speakerRole: Literal["judge", "plaintiff", "defendant"]
    contentSource: Literal["case"]
    instruction: text_type(4000)


class CivilProcedureStepV2(StrictModel):
    name: text_type(256)
    type: Literal["sequence"]
    segments: list[CivilSegmentRequirementV2] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_segments(self):
        names = [item.name for item in self.segments]
        if len(names) != len(set(names)):
            raise ValueError("duplicate segment name")
        for item in self.segments:
            if " / " in item.name or "{" in item.name or "}" in item.name:
                raise ValueError("reserved name characters")
        return self


class CivilProcedurePhaseV2(StrictModel):
    name: text_type(256)
    steps: list[CivilProcedureStepV2] = Field(min_length=1, max_length=100)


class CivilProcedureV2(StrictModel):
    phases: list[CivilProcedurePhaseV2] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_names(self):
        phases = [item.name for item in self.phases]
        steps = [step.name for phase in self.phases for step in phase.steps]
        if len(phases) != len(set(phases)) or len(steps) != len(set(steps)):
            raise ValueError("duplicate phase or step name")
        if any(" / " in name or "{" in name or "}" in name for name in phases + steps):
            raise ValueError("reserved name characters")
        if sum(len(step.segments) for phase in self.phases for step in phase.steps) > 200:
            raise ValueError("too many segment requirements")
        return self


class CivilCaseDraftGenerateRequestV2(StrictModel):
    documents: list[CivilSourceDocumentV2] = Field(min_length=1, max_length=22)
    procedure: CivilProcedureV2


class CivilPartyV2(StrictModel):
    name: str = Field(max_length=256)
    entityType: EntityType | None
    description: str = Field(max_length=1000)


class CivilMoneyComponentV2(StrictModel):
    name: text_type(128)
    amountFen: int = Field(ge=0)


class CivilMoneyV2(StrictModel):
    totalAmountFen: int = Field(ge=0)
    components: list[CivilMoneyComponentV2] = Field(max_length=20)

    @model_validator(mode="after")
    def components_match_total(self):
        if self.components and sum(item.amountFen for item in self.components) != self.totalAmountFen:
            raise ValueError("money components must sum to totalAmountFen")
        return self


class CivilClaimV2(StrictModel):
    category: ClaimCategory
    text: text_type(2000)
    amount: CivilMoneyV2 | None

    @model_validator(mode="after")
    def monetary_shape(self):
        if self.amount is not None and self.category != "monetary_compensation":
            raise ValueError("only monetary_compensation may have amount")
        return self


class CivilEvidenceMaterialV2(StrictModel):
    name: text_type(256)
    source: text_type(512)
    displayText: text_type(4000)


class CivilEvidenceGroupV2(StrictModel):
    side: Side
    name: text_type(256)
    proofPurpose: text_type(1000)
    materials: list[CivilEvidenceMaterialV2] = Field(min_length=1, max_length=30)


class CivilSegmentContentV2(StrictModel):
    stepName: text_type(256)
    segmentName: text_type(1024)
    speakerRole: Literal["judge", "plaintiff", "defendant"]
    text: str = Field(max_length=8000)


class CivilCaseDraftV2(StrictModel):
    causeOfAction: str = Field(max_length=512)
    subjectMatter: str = Field(max_length=1000)
    summary: str = Field(max_length=4000)
    plaintiff: CivilPartyV2
    defendant: CivilPartyV2
    claims: list[CivilClaimV2] = Field(max_length=30)
    defenses: list[text_type(2000)] = Field(max_length=30)
    disputeFocuses: list[text_type(1000)] = Field(max_length=20)
    evidenceGroups: list[CivilEvidenceGroupV2] = Field(max_length=30)
    segmentContents: list[CivilSegmentContentV2] = Field(max_length=2000)


class CivilGenerationIssueV2(StrictModel):
    severity: Literal["blocking", "warning"]
    code: text_type(64)
    message: text_type(1000)


class CivilCaseDraftGenerateResponseV2(StrictModel):
    draft: CivilCaseDraftV2
    issues: list[CivilGenerationIssueV2] = Field(max_length=100)

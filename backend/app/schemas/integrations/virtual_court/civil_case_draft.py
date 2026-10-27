"""Civil case draft generation V1: source text in, reviewable semantics out.

This is an offline contract. No API route or model execution is registered here.
"""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .judge import StrictModel, text_type


CIVIL_DRAFT_RESPONSE_MAX_BYTES = 524288


Side = Literal["plaintiff", "defendant"]
EntityType = Literal["natural_person", "legal_entity"]
SourceKey = Annotated[
    str,
    Field(max_length=64, pattern=r"^(plaintiffComplaint|defendantAnswer|otherMaterials\[(0|[1-9][0-9]*)\])$"),
]
ClaimCategory = Literal[
    "cease_infringement", "public_apology", "monetary_compensation", "litigation_costs"
]


class CivilOtherMaterialV1(StrictModel):
    name: text_type(256)
    text: text_type(60000)


class CivilCaseDraftGenerateRequestV1(StrictModel):
    plaintiffComplaint: text_type(60000)
    defendantAnswer: text_type(60000)
    otherMaterials: list[CivilOtherMaterialV1] = Field(max_length=20)


class CivilSourceRefV1(StrictModel):
    sourceKey: SourceKey
    quote: text_type(1000)


class CivilFieldSourceV1(CivilSourceRefV1):
    fieldPath: Annotated[str, Field(min_length=2, max_length=256, pattern=r"^/")]


class CivilPartyV1(StrictModel):
    name: str = Field(max_length=256)
    entityType: EntityType | None
    description: str = Field(max_length=1000)


class CivilMoneyComponentV1(StrictModel):
    name: text_type(128)
    amountFen: int = Field(ge=0)


class CivilMoneyV1(StrictModel):
    totalAmountFen: int = Field(ge=0)
    components: list[CivilMoneyComponentV1] = Field(max_length=20)

    @model_validator(mode="after")
    def components_match_total(self):
        if self.components and sum(item.amountFen for item in self.components) != self.totalAmountFen:
            raise ValueError("money components must sum to totalAmountFen")
        return self


class CivilClaimV1(StrictModel):
    category: ClaimCategory
    text: text_type(2000)
    amount: CivilMoneyV1 | None

    @model_validator(mode="after")
    def monetary_shape(self):
        if self.amount is not None and self.category != "monetary_compensation":
            raise ValueError("only monetary_compensation may have amount")
        return self


class CivilEvidenceMaterialV1(StrictModel):
    name: text_type(256)
    source: str = Field(max_length=512)
    displayText: text_type(4000)


class CivilEvidenceGroupV1(StrictModel):
    side: Side
    name: text_type(256)
    proofPurpose: text_type(1000)
    materials: list[CivilEvidenceMaterialV1] = Field(min_length=1, max_length=30)
    offerSpeech: str = Field(max_length=4000)
    crossSpeech: str = Field(max_length=4000)


class CivilFixedSpeechesV1(StrictModel):
    plaintiffClaim: str = Field(max_length=4000)
    defendantAnswer: str = Field(max_length=4000)
    plaintiffFocus: str = Field(max_length=4000)
    defendantFocus: str = Field(max_length=4000)
    plaintiffFinal: str = Field(max_length=4000)
    defendantFinal: str = Field(max_length=4000)


class CivilCaseDraftV1(StrictModel):
    causeOfAction: str = Field(max_length=512)
    subjectMatter: str = Field(max_length=1000)
    summary: str = Field(max_length=4000)
    plaintiff: CivilPartyV1
    defendant: CivilPartyV1
    claims: list[CivilClaimV1] = Field(max_length=30)
    defenses: list[text_type(2000)] = Field(max_length=30)
    disputeFocuses: list[text_type(1000)] = Field(max_length=20)
    evidenceGroups: list[CivilEvidenceGroupV1] = Field(max_length=30)
    fixedSpeeches: CivilFixedSpeechesV1


class CivilGenerationIssueV1(StrictModel):
    severity: Literal["blocking", "warning"]
    code: text_type(64)
    message: text_type(1000)
    sources: list[CivilSourceRefV1] = Field(max_length=10)


class CivilCaseDraftGenerateResponseV1(StrictModel):
    draft: CivilCaseDraftV1
    issues: list[CivilGenerationIssueV1] = Field(max_length=100)
    sourceRefs: list[CivilFieldSourceV1] = Field(max_length=300)

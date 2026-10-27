"""Executable shape checks for the frozen civil draft generation contract."""

import copy

import pytest
from pydantic import ValidationError

from app.schemas.integrations.virtual_court import (
    CivilCaseDraftGenerateRequestV1,
    CivilCaseDraftGenerateResponseV1,
)


REQUEST = {
    "plaintiffComplaint": "原告林某请求赔偿经济损失20000元。",
    "defendantAnswer": "被告认为赔偿过高。",
    "otherMaterials": [{"name": "原告证据.md", "text": "律师费票据金额6000元。"}],
}

RESPONSE = {
    "draft": {
        "causeOfAction": "著作权侵权纠纷",
        "subjectMatter": "《山海鹿鸣》",
        "summary": "原告主张著作权侵权，被告认为赔偿过高。",
        "plaintiff": {"name": "林某", "entityType": "natural_person", "description": ""},
        "defendant": {"name": "", "entityType": None, "description": ""},
        "claims": [{
            "category": "monetary_compensation",
            "text": "赔偿经济损失20000元。",
            "amount": {"totalAmountFen": 2000000, "components": [
                {"name": "经济损失", "amountFen": 2000000}
            ]},
        }],
        "defenses": ["赔偿过高"],
        "disputeFocuses": ["合理赔偿金额"],
        "evidenceGroups": [{
            "side": "plaintiff",
            "name": "维权费用",
            "proofPurpose": "证明律师费支出",
            "materials": [{"name": "律师费票据摘录", "source": "原告提供", "displayText": "票据文字摘录：律师费6000元。"}],
            "offerSpeech": "原告提交律师费票据文字摘录。",
            "crossSpeech": "被告请原告说明票据原件。",
        }],
        "fixedSpeeches": {
            "plaintiffClaim": "原告请求赔偿。",
            "defendantAnswer": "被告认为赔偿过高。",
            "plaintiffFocus": "原告认为损失应获赔偿。",
            "defendantFocus": "被告对金额有异议。",
            "plaintiffFinal": "请支持诉请。",
            "defendantFinal": "请酌情认定。",
        },
    },
    "issues": [{
        "severity": "blocking",
        "code": "DEFENDANT_NAME_MISSING",
        "message": "答辩状未写明被告名称。",
    }],
}


def test_v1_accepts_text_inputs_and_partial_review_draft():
    assert CivilCaseDraftGenerateRequestV1.model_validate(REQUEST).otherMaterials[0].name == "原告证据.md"
    response = CivilCaseDraftGenerateResponseV1.model_validate(RESPONSE)
    assert response.draft.defendant.name == ""
    assert response.issues[0].severity == "blocking"


@pytest.mark.parametrize("section,key,value", [
    ("request", "caseId", "case-123"),
    ("response", "procedureId", "civil-v1"),
])
def test_v1_rejects_system_owned_fields(section, key, value):
    payload = copy.deepcopy(REQUEST if section == "request" else RESPONSE)
    payload[key] = value
    model = CivilCaseDraftGenerateRequestV1 if section == "request" else CivilCaseDraftGenerateResponseV1
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_v1_rejects_inconsistent_amount():
    payload = copy.deepcopy(RESPONSE)
    payload["draft"]["claims"][0]["amount"]["totalAmountFen"] = 2800000
    with pytest.raises(ValidationError):
        CivilCaseDraftGenerateResponseV1.model_validate(payload)


def test_v1_rejects_unrequested_fields_and_dynamic_script():
    payload = copy.deepcopy(RESPONSE)
    payload["sourceRefs"] = []
    with pytest.raises(ValidationError):
        CivilCaseDraftGenerateResponseV1.model_validate(payload)
    payload = copy.deepcopy(RESPONSE)
    payload["draft"]["inquiryAnswers"] = ["预生成回答"]
    with pytest.raises(ValidationError):
        CivilCaseDraftGenerateResponseV1.model_validate(payload)

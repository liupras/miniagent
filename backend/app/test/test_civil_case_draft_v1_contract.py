"""Civil draft contract: fixed segments and reviewable evidence materials."""
import copy
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from app.schemas.integrations.virtual_court import CivilCaseDraftGenerateRequestV2, CivilCaseDraftGenerateResponseV2
from app.services.virtual_court import validate_civil_draft_agent_output, CivilDraftInvalidResponseError

FIXTURE = json.loads((Path(__file__).parent / "fixtures/civil_draft_v2/contract.json").read_text(encoding="utf-8"))
REQUEST, RESPONSE = FIXTURE["request"], FIXTURE["response"]

def validate(payload):
    return validate_civil_draft_agent_output(json.dumps(payload, ensure_ascii=False),
        CivilCaseDraftGenerateRequestV2.model_validate(REQUEST))

def test_named_segments_cover_requested_procedure():
    result = validate(RESPONSE)
    assert len(result.draft.segmentContents) == 7
    assert result.draft.segmentContents[-1].speakerRole == "defendant"
    assert result.draft.evidenceGroups[0].materials[0].displayText

@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra", "role", "rename"])
def test_rejects_wrong_segment_association(mutation):
    payload = copy.deepcopy(RESPONSE)
    contents = payload["draft"]["segmentContents"]
    if mutation == "missing": contents.pop()
    elif mutation == "duplicate": contents.append(copy.deepcopy(contents[0]))
    elif mutation == "extra": contents.append(dict(contents[0], segmentName="动态询问"))
    elif mutation == "role": contents[-1]["speakerRole"] = "plaintiff"
    else: contents[0]["stepName"] = "模型自定义名称"
    with pytest.raises(CivilDraftInvalidResponseError): validate(payload)

def test_order_does_not_determine_association():
    payload = copy.deepcopy(RESPONSE)
    payload["draft"]["segmentContents"].reverse()
    assert validate(payload).draft.segmentContents

def test_blank_text_requires_business_blocking_issue():
    payload = copy.deepcopy(RESPONSE)
    payload["draft"]["segmentContents"][0]["text"] = ""
    assert validate(payload).issues
    payload["issues"] = []
    with pytest.raises(CivilDraftInvalidResponseError): validate(payload)

def test_duplicate_group_and_old_speech_fields_are_rejected():
    payload = copy.deepcopy(RESPONSE)
    payload["draft"]["evidenceGroups"] *= 2
    with pytest.raises(CivilDraftInvalidResponseError): validate(payload)
    for key in ("fixedSpeeches", "inquiryAnswers", "demoScript"):
        payload = copy.deepcopy(RESPONSE)
        payload["draft"][key] = {}
        with pytest.raises(ValidationError): CivilCaseDraftGenerateResponseV2.model_validate(payload)
    payload = copy.deepcopy(RESPONSE)
    payload["draft"]["evidenceGroups"][0]["offerSpeech"] = "old"
    with pytest.raises(ValidationError): CivilCaseDraftGenerateResponseV2.model_validate(payload)
    payload = copy.deepcopy(RESPONSE)
    payload["draft"]["evidenceGroups"][0]["materials"][0]["displayText"] = ""
    with pytest.raises(ValidationError): CivilCaseDraftGenerateResponseV2.model_validate(payload)
    payload = copy.deepcopy(RESPONSE)
    payload["draft"]["evidenceGroups"][0]["materials"][0]["source"] = ""
    with pytest.raises(ValidationError): CivilCaseDraftGenerateResponseV2.model_validate(payload)

@pytest.mark.parametrize("mutation", ["no_procedure", "duplicate_step", "duplicate_segment", "bad_role", "bad_source", "bad_template", "evidence_loop"])
def test_request_configuration_is_validated(mutation):
    payload = copy.deepcopy(REQUEST)
    step = payload["procedure"]["phases"][0]["steps"][0]
    if mutation == "no_procedure": payload.pop("procedure")
    elif mutation == "duplicate_step": payload["procedure"]["phases"][0]["steps"].append(copy.deepcopy(step))
    elif mutation == "duplicate_segment": step["segments"].append(copy.deepcopy(step["segments"][0]))
    elif mutation == "bad_role": step["segments"][0]["speakerRole"] = "offeringParty"
    elif mutation == "bad_source": step["segments"][0]["contentSource"] = "caseEvidence"
    elif mutation == "evidence_loop": step["type"] = "evidenceGroupLoop"
    else: step["segments"][0]["name"] = "{未知模板}"
    with pytest.raises(ValidationError): CivilCaseDraftGenerateRequestV2.model_validate(payload)

def test_same_segment_name_in_different_steps_is_allowed():
    payload = copy.deepcopy(REQUEST)
    phase = payload["procedure"]["phases"][0]
    other = copy.deepcopy(phase["steps"][0]); other["name"] += "补充"
    phase["steps"].append(other)
    assert CivilCaseDraftGenerateRequestV2.model_validate(payload)

def test_amount_and_document_limits_are_preserved():
    payload = copy.deepcopy(RESPONSE)
    payload["draft"]["claims"][0]["amount"]["totalAmountFen"] += 1
    with pytest.raises(ValidationError): CivilCaseDraftGenerateResponseV2.model_validate(payload)
    for docs in ([], [{"name":"材料", "text":""}], REQUEST["documents"] * 8):
        with pytest.raises(ValidationError):
            CivilCaseDraftGenerateRequestV2.model_validate(dict(REQUEST, documents=docs))

"""Frozen shared case draft contract and case-type-neutral validation."""

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.schemas.integrations.virtual_court import CaseDraftGenerateRequestV1
from app.services.virtual_court import (
    CaseDraftInvalidResponseError,
    validate_case_draft_agent_output,
)


FIXTURE = json.loads((Path(__file__).parent / "fixtures/case_draft_v1/civil-contract-v1.json").read_text(encoding="utf-8"))
REQUEST, RESPONSE = FIXTURE["request"], FIXTURE["response"]


def validate_output(request, output):
    return validate_case_draft_agent_output(
        json.dumps(output, ensure_ascii=False), CaseDraftGenerateRequestV1.model_validate(request)
    )


def test_shared_civil_contract_is_valid():
    request = CaseDraftGenerateRequestV1.model_validate(REQUEST)
    response = validate_output(REQUEST, RESPONSE)
    assert request.draftContract.contractId == "civil-case-draft-v1"
    assert len(response.draft["segmentContents"]) == 7
    assert response.issues[0].severity == "blocking"
    Draft202012Validator.check_schema(request.draftContract.draftSchema)


def test_other_draft_shape_needs_no_civil_validator():
    request = copy.deepcopy(REQUEST)
    request["draftContract"] = {
        "contractId": "sample-case-draft-v1",
        "draftSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["finding"],
            "properties": {"finding": {"type": "string", "minLength": 1}},
        },
        "instructions": ["只依据材料归纳 finding。"],
    }
    request["context"] = {"topic": "模拟案件"}
    assert validate_output(request, {"draft": {"finding": "材料显示存在争议。"}, "issues": []}).draft
    with pytest.raises(CaseDraftInvalidResponseError):
        validate_output(request, RESPONSE)


@pytest.mark.parametrize("mutation", ["extra", "missing", "amount", "issue", "duplicate"])
def test_model_output_must_match_both_schemas(mutation):
    output = copy.deepcopy(RESPONSE)
    if mutation == "extra":
        output["draft"]["unsupported"] = "x"
    elif mutation == "missing":
        del output["draft"]["claims"]
    elif mutation == "amount":
        output["draft"]["claims"][0]["amount"]["totalAmountFen"] = -1
    elif mutation == "issue":
        output["issues"][0]["severity"] = "info"
    else:
        raw = '{"draft":{},"draft":{},"issues":[]}'
        with pytest.raises(CaseDraftInvalidResponseError):
            validate_case_draft_agent_output(raw, CaseDraftGenerateRequestV1.model_validate(REQUEST))
        return
    with pytest.raises(CaseDraftInvalidResponseError):
        validate_output(REQUEST, output)


@pytest.mark.parametrize("change", ["remote_ref", "missing_ref", "cyclic_ref", "dynamic_ref", "bad_meta", "duplicate_source"])
def test_rejects_unsafe_or_invalid_request(change):
    request = copy.deepcopy(REQUEST)
    schema = request["draftContract"]["draftSchema"]
    if change == "remote_ref":
        schema["properties"]["summary"] = {"$ref": "https://example.com/schema.json"}
    elif change == "missing_ref":
        schema["properties"]["summary"] = {"$ref": "#/$defs/absent"}
    elif change == "cyclic_ref":
        schema["$defs"]["loop"] = {"$ref": "#/$defs/loop"}
    elif change == "dynamic_ref":
        schema["properties"]["summary"] = {"$dynamicRef": "#loop"}
    elif change == "bad_meta":
        schema["$schema"] = "https://json-schema.org/draft/2019-09/schema"
    else:
        request["documents"][1]["sourceId"] = request["documents"][0]["sourceId"]
    with pytest.raises(ValidationError):
        CaseDraftGenerateRequestV1.model_validate(request)


def test_request_byte_limits():
    request = copy.deepcopy(REQUEST)
    request["context"] = {"long": "文" * 50_000}
    with pytest.raises(ValidationError):
        CaseDraftGenerateRequestV1.model_validate(request)
    request = copy.deepcopy(REQUEST)
    request["documents"] = [
        {"sourceId": str(index), "name": "材料", "text": "文" * 60_000}
        for index in range(4)
    ]
    with pytest.raises(ValidationError):
        CaseDraftGenerateRequestV1.model_validate(request)

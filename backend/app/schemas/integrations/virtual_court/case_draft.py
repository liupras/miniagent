"""Case-type-neutral draft generation request and response contracts."""

import json
from typing import Any, Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import Field, model_validator

from .judge import StrictModel, text_type


REQUEST_MAX_BYTES = 1_048_576
RESPONSE_MAX_BYTES = 524_288
DOCUMENTS_MAX_BYTES = 524_288
CONTRACT_MAX_BYTES = 131_072
CONTEXT_MAX_BYTES = 131_072
SCHEMA_MAX_DEPTH = 32


def json_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def resolve_local_ref(schema: dict, reference: str):
    if not reference.startswith("#/$defs/"):
        raise ValueError("draftSchema only permits local $defs references")
    target = schema
    for escaped in reference[2:].split("/"):
        key = escaped.replace("~1", "/").replace("~0", "~")
        if not isinstance(target, dict) or key not in target:
            raise ValueError("draftSchema contains an unresolved $ref")
        target = target[key]
    return target


def check_schema_boundary(schema: dict):
    if (schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
            or schema.get("type") != "object"
            or schema.get("additionalProperties") is not False
            or not isinstance(schema.get("properties"), dict)
            or not isinstance(schema.get("required"), list)):
        raise ValueError("draftSchema must be a closed Draft 2020-12 object schema")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError("draftSchema is not valid Draft 2020-12") from exc

    def walk(node, depth, active_refs):
        if depth > SCHEMA_MAX_DEPTH:
            raise ValueError("draftSchema exceeds maximum depth")
        if isinstance(node, dict):
            if any(key in node for key in ("$dynamicRef", "$recursiveRef", "$anchor", "$dynamicAnchor")):
                raise ValueError("draftSchema contains unsupported dynamic references")
            if depth and "$id" in node:
                raise ValueError("draftSchema cannot redefine $id below its root")
            reference = node.get("$ref")
            if reference is not None:
                if not isinstance(reference, str) or reference in active_refs:
                    raise ValueError("draftSchema contains an invalid or cyclic $ref")
                walk(resolve_local_ref(schema, reference), depth + 1, active_refs | {reference})
            for key, value in node.items():
                if key != "$ref":
                    walk(value, depth + 1, active_refs)
        elif isinstance(node, list):
            for value in node:
                walk(value, depth + 1, active_refs)

    walk(schema, 0, set())


class CaseDraftContractV1(StrictModel):
    contractId: str = Field(pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*-v[1-9][0-9]*$", max_length=128)
    draftSchema: dict[str, Any]
    instructions: list[text_type(4000)] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_contract(self):
        value = self.model_dump(mode="json")
        if json_bytes(value) > CONTRACT_MAX_BYTES:
            raise ValueError("draftContract exceeds maximum size")
        check_schema_boundary(self.draftSchema)
        return self


class CaseDraftDocumentV1(StrictModel):
    sourceId: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$", max_length=128)
    name: text_type(256)
    text: text_type(60000)


class CaseDraftGenerateRequestV1(StrictModel):
    draftContract: CaseDraftContractV1
    documents: list[CaseDraftDocumentV1] = Field(min_length=1, max_length=22)
    context: dict[str, Any]

    @model_validator(mode="after")
    def validate_limits(self):
        ids = [item.sourceId for item in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("document sourceId values must be unique")
        if sum(len(item.text.encode("utf-8")) for item in self.documents) > DOCUMENTS_MAX_BYTES:
            raise ValueError("document text exceeds total byte limit")
        if json_bytes(self.context) > CONTEXT_MAX_BYTES:
            raise ValueError("context exceeds maximum size")
        return self


class CaseDraftIssueV1(StrictModel):
    severity: Literal["blocking", "warning"]
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    message: text_type(1000)


class CaseDraftGenerateResponseV1(StrictModel):
    draft: dict[str, Any]
    issues: list[CaseDraftIssueV1] = Field(max_length=100)

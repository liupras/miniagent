"""Frozen TranscriptAPI V2 contract checks.

These tests validate schemas and fixture integrity. They do not claim that the
endpoint, dedicated agent, or model semantics are implemented.
"""
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parent / "fixtures/transcript_v2"
PROTOCOL = (
    Path(__file__).parents[1]
    / "api/integrations/virtual_court/TRANSCRIPT_PROTOCOL_V2.md"
)


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_transcript_fixture_oracle():
    spec = importlib.util.spec_from_file_location(
        "transcript_v2_fixture_oracle", ROOT / "verify_fixtures.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.main() == 0


def test_transcript_contract_has_minimal_top_level_shape():
    request = load("schemas/transcript-request.schema.json")
    response = load("schemas/transcript-response.schema.json")

    assert set(request["properties"]) == {
        "state_version",
        "case_context",
        "records",
    }
    assert set(request["required"]) == set(request["properties"])
    assert set(response["properties"]) == {"state_version", "transcript"}
    assert set(response["required"]) == set(response["properties"])
    assert request["additionalProperties"] is False
    assert response["additionalProperties"] is False


def test_transcript_material_shape_matches_frozen_judge_shape():
    transcript = load("schemas/transcript-request.schema.json")
    judge = load(
        "../judge_v2_split_endpoints/schemas/next-action-request.schema.json"
    )

    assert transcript["properties"]["case_context"] == judge["properties"]["case_context"]
    assert transcript["properties"]["records"] == judge["properties"]["records"]


def test_fixture_matrix_covers_required_protocol_edges():
    manifest = load("manifest.json")
    ids = {case["id"] for case in manifest["cases"]}
    required = {
        "transcript-speech-request",
        "transcript-summary-request",
        "transcript-duplicate-key",
        "transcript-request-body-max",
        "transcript-request-body-over-max",
        "transcript-content-budget-over",
        "transcript-response",
        "transcript-response-stale",
        "transcript-response-text-max",
        "transcript-response-text-over-max",
        "transcript-response-body-max",
        "transcript-response-body-over-max",
    }
    assert required <= ids


def test_protocol_snapshot_matches_design_document_at_freeze_time():
    assert (ROOT / "protocol-frozen.md").read_bytes() == PROTOCOL.read_bytes()

"""Frozen split-endpoint JudgeAPI V2 contract checks.

These tests validate schemas and fixture integrity. They do not claim that the
new endpoints, model semantics, tool policy, or VirtualCourt flow are implemented.
"""
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parent / "fixtures/judge_v2_split_endpoints"


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_split_endpoint_fixture_oracle():
    spec = importlib.util.spec_from_file_location(
        "judge_v2_split_fixture_oracle", ROOT / "verify_fixtures.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.main() == 0


def test_law_check_contract_is_structurally_isolated():
    request = load("schemas/law-check-request.schema.json")
    response = load("schemas/law-check-response.schema.json")
    assert set(request["properties"]) == {"state_version", "role", "text", "context"}
    assert set(request["required"]) == {"state_version", "role", "text"}
    assert "target" not in response["properties"]
    assert response["properties"]["decision"]["enum"] == [
        "NO_ACTION",
        "EXPLAIN_LAW",
        "HANDOFF",
    ]


def test_next_action_contract_excludes_law_decisions():
    request = load("schemas/next-action-request.schema.json")
    response = load("schemas/next-action-response.schema.json")
    action_values = request["properties"]["allowed_actions"]["items"]["enum"]
    response_values = response["properties"]["decision"]["enum"]
    assert "NO_ACTION" not in action_values + response_values
    assert "EXPLAIN_LAW" not in action_values + response_values
    assert "phase" not in request["properties"]
    assert action_values == ["ASK", "COMPLETE", "HANDOFF"]
    assert response_values == ["ASK", "COMPLETE", "HANDOFF"]
    assert "current_issue" not in request["properties"]
    assert "investigation_summary" not in request["properties"]["case_context"]["properties"]

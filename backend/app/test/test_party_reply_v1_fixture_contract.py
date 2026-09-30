"""Frozen Party Reply API V1 fixture checks.

These tests validate schemas, samples and integrity. They do not claim that the
HTTP route, model execution or VirtualCourt automatic-reply flow is implemented.
"""
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parent / "fixtures/party_reply_v1"


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_party_reply_fixture_oracle():
    spec = importlib.util.spec_from_file_location(
        "party_reply_v1_fixture_oracle", ROOT / "verify_fixtures.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.main() == 0


def test_party_reply_contract_has_only_frozen_fields():
    request = load("schemas/request.schema.json")
    response = load("schemas/response.schema.json")
    assert set(request["properties"]) == {
        "state_version", "role", "question", "case_context", "records"
    }
    assert set(request["required"]) == set(request["properties"])
    assert request["properties"]["role"]["enum"] == ["PLAINTIFF", "DEFENDANT"]
    assert set(response["properties"]) == {"state_version", "speech"}
    assert set(response["required"]) == set(response["properties"])
    assert "answer_policy" not in request["properties"]


def test_server_owns_preset_first_behavior():
    scenarios = {item["id"] for item in load("behavior-scenarios.json")["scenarios"]}
    assert {
        "automatic-preset-match",
        "automatic-preset-miss",
        "manual-no-call",
        "manual-to-automatic",
        "automatic-to-manual",
        "human-answer-wins",
        "authority-context-changed",
        "answer-quality",
    } <= scenarios

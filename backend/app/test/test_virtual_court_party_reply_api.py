import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.exception_handlers import register_global_exception_handlers
from app.api.integrations.errors import register_integration_exception_handlers
from app.api.integrations.virtual_court.party import router
from app.core.config import settings
from app.schemas.integrations.virtual_court import PartyReplyResponseV1
from app.services.virtual_court import (
    PartyReplyConfigurationError,
    PartyReplyContextError,
    PartyReplyInvalidResponseError,
    PartyReplyTimeoutError,
    PartyReplyUnavailableError,
)


ROOT = Path(__file__).parent / "fixtures" / "party_reply_v1"
PREFIX = "/api/v2/integrations/virtual-court"
ENDPOINT = PREFIX + "/party/reply"
HEADERS = {
    "Authorization": "Bearer test-only",
    "Content-Type": "application/json",
}


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class ServiceStub:
    def __init__(self, error=None):
        self.error = error
        self.requests = []

    async def reply(self, body):
        self.requests.append(body)
        if self.error:
            raise self.error
        return PartyReplyResponseV1(
            state_version=body.state_version,
            speech="现有材料显示，本方没有核验页面展示的授权范围。",
        )


def client(service=None):
    app = FastAPI()
    app.state.container = SimpleNamespace(
        party_reply_service=service or ServiceStub()
    )
    app.include_router(router, prefix=PREFIX)
    register_global_exception_handlers(app)
    register_integration_exception_handlers(app)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setattr(
        settings,
        "virtual_court_internal_service_token",
        SecretStr("test-only"),
    )


REQUEST_CASES = [
    case for case in load("manifest.json")["cases"] if case["kind"] == "request"
]


@pytest.mark.parametrize("case", REQUEST_CASES, ids=lambda case: case["id"])
def test_frozen_requests_through_http_route(case):
    service = ServiceStub()
    response = client(service).post(
        ENDPOINT,
        headers=HEADERS,
        content=(ROOT / case["file"]).read_bytes(),
    )

    assert response.status_code == (200 if case["valid"] else 422), response.text
    assert len(service.requests) == int(case["valid"])
    if case["valid"]:
        assert response.json()["state_version"] == service.requests[0].state_version
    else:
        assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_route_requires_internal_service_token():
    body = load("cases/defendant-request.json")
    for headers in ({}, {"Authorization": "Bearer wrong"}):
        response = client().post(ENDPOINT, headers=headers, json=body)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


@pytest.mark.parametrize(
    "error,status,code,retryable",
    [
        (PartyReplyContextError(params={"reason": "model_context_budget"}), 422, "INVALID_REQUEST", False),
        (PartyReplyConfigurationError(params={"reason": "agent_unavailable"}), 503, "SERVICE_UNAVAILABLE", False),
        (PartyReplyUnavailableError(), 503, "SERVICE_UNAVAILABLE", True),
        (PartyReplyTimeoutError(params={"timeout": 120}), 504, "UPSTREAM_TIMEOUT", True),
        (PartyReplyInvalidResponseError(params={"reason": "schema_validation_failed"}), 502, "MODEL_RESPONSE_INVALID", True),
    ],
)
def test_party_reply_exception_mapping(error, status, code, retryable):
    response = client(ServiceStub(error)).post(
        ENDPOINT,
        headers=HEADERS,
        json=load("cases/defendant-request.json"),
    )
    assert response.status_code == status
    payload = response.json()["error"]
    assert payload["code"] == code
    assert payload["retryable"] is retryable


def test_openapi_and_application_register_minimal_contract():
    schema = client().get("/openapi.json").json()
    assert set(schema["components"]["schemas"]["PartyReplyRequestV1"]["properties"]) == {
        "state_version", "role", "question", "case_context", "records"
    }
    assert set(schema["components"]["schemas"]["PartyReplyResponseV1"]["properties"]) == {
        "state_version", "speech"
    }

    main_source = (Path(__file__).parents[1] / "main.py").read_text(
        encoding="utf-8"
    )
    assert "virtual_court_party_router" in main_source
    assert 'prefix="/api/v2/integrations/virtual-court"' in main_source
    container_source = (
        Path(__file__).parents[1] / "core" / "service_container.py"
    ).read_text(encoding="utf-8")
    assert "self.party_reply_service = PartyReplyService(" in container_source


def test_route_logs_metadata_but_not_payloads():
    source = (
        Path(__file__).parents[1] / "api/integrations/virtual_court/party.py"
    ).read_text(encoding="utf-8")
    assert "[PartyReplyV1]" in source
    assert "question_codepoints" in source
    assert "model_dump_json" not in source

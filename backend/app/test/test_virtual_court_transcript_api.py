"""TranscriptAPI V2 HTTP contract and integration-boundary behavior."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.exception_handlers import register_global_exception_handlers
from app.api.integrations.errors import register_integration_exception_handlers
from app.api.integrations.virtual_court.transcript import router
from app.core.config import settings
from app.schemas.integrations.virtual_court import TranscriptGenerateResponseV2
from app.services.virtual_court import (
    TranscriptConfigurationError,
    TranscriptContextError,
    TranscriptInvalidResponseError,
    TranscriptTimeoutError,
    TranscriptUnavailableError,
)


ROOT = Path(__file__).parent / "fixtures" / "transcript_v2"
PREFIX = "/api/v2/integrations/virtual-court"
ENDPOINT = PREFIX + "/transcript/generate"
HEADERS = {
    "X-Integration-Key": "test-only",
    "Content-Type": "application/json",
}


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class TranscriptServiceStub:
    def __init__(self, error=None):
        self.error = error
        self.requests = []

    async def generate(self, body):
        self.requests.append(body)
        if self.error:
            raise self.error
        return TranscriptGenerateResponseV2(
            state_version=body.state_version,
            transcript="庭审笔录\n\n本响应由测试服务生成。",
        )


def client(service=None):
    app = FastAPI()
    app.state.container = SimpleNamespace(
        transcript_service=service or TranscriptServiceStub()
    )
    app.include_router(router, prefix=PREFIX)
    register_global_exception_handlers(app)
    register_integration_exception_handlers(app)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setattr(
        settings,
        "virtual_court_api_key",
        SecretStr("test-only"),
    )


REQUEST_CASES = [
    case
    for case in load("manifest.json")["cases"]
    if case["kind"] == "request"
]


@pytest.mark.parametrize("case", REQUEST_CASES, ids=lambda case: case["id"])
def test_frozen_requests_through_http_route(case):
    service = TranscriptServiceStub()
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


def test_route_requires_integration_key():
    body = load("cases/transcript-speech-request.json")
    for headers in ({}, {"X-Integration-Key": "wrong"}):
        response = client().post(ENDPOINT, headers=headers, json=body)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


def test_unconfigured_integration_key_is_503(monkeypatch):
    monkeypatch.setattr(settings, "virtual_court_api_key", SecretStr(""))
    response = client().post(
        ENDPOINT,
        headers=HEADERS,
        json=load("cases/transcript-speech-request.json"),
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


@pytest.mark.parametrize(
    "error,status,code,retryable",
    [
        (
            TranscriptInvalidResponseError(
                params={"reason": "schema_validation_failed", "field": "transcript"}
            ),
            502,
            "MODEL_RESPONSE_INVALID",
            True,
        ),
        (
            TranscriptContextError(
                params={"reason": "model_context_budget", "field": "records"}
            ),
            422,
            "INVALID_REQUEST",
            False,
        ),
        (
            TranscriptConfigurationError(params={"reason": "agent_unavailable"}),
            503,
            "SERVICE_UNAVAILABLE",
            False,
        ),
        (TranscriptUnavailableError(), 503, "SERVICE_UNAVAILABLE", True),
        (
            TranscriptTimeoutError(params={"timeout": 180}),
            504,
            "UPSTREAM_TIMEOUT",
            True,
        ),
    ],
)
def test_transcript_exception_mapping(error, status, code, retryable):
    response = client(TranscriptServiceStub(error)).post(
        ENDPOINT,
        headers=HEADERS,
        json=load("cases/transcript-speech-request.json"),
    )
    assert response.status_code == status
    payload = response.json()["error"]
    assert payload["code"] == code
    assert payload["retryable"] is retryable
    if error.params.get("reason"):
        assert payload["details"]["reason"] == error.params["reason"]


def test_openapi_has_minimal_transcript_contract():
    schema = client().get("/openapi.json").json()
    assert ENDPOINT in schema["paths"]
    components = schema["components"]["schemas"]
    assert set(components["TranscriptGenerateRequestV2"]["properties"]) == {
        "state_version",
        "case_context",
        "records",
    }
    assert set(components["TranscriptGenerateResponseV2"]["properties"]) == {
        "state_version",
        "transcript",
    }


def test_main_and_container_register_transcript_components():
    from app.main import app as main_app

    assert ENDPOINT in main_app.openapi()["paths"]
    container_source = (
        Path(__file__).parents[1] / "core" / "service_container.py"
    ).read_text(encoding="utf-8")
    assert "self.transcript_service = TranscriptService(" in container_source


def test_route_logs_metadata_but_not_payloads():
    source = (
        Path(__file__).parents[1]
        / "api/integrations/virtual_court/transcript.py"
    ).read_text(encoding="utf-8")
    assert "[TranscriptV2]" in source
    assert "material_codepoints" in source
    assert "model_dump_json" not in source

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.i18n import error_translation
from app.api.integrations.errors import register_integration_exception_handlers
from app.api.integrations.virtual_court.judge import router
from app.core.config import settings
from app.schemas.integrations.virtual_court import JudgeDecisionResponse
from app.services.virtual_court import (
    JudgeConfigurationError,
    JudgeInvalidResponseError,
    JudgeServiceError,
    JudgeTimeoutError,
    JudgeUnavailableError,
)


API_PREFIX = "/api/v1/integrations/virtual-court"
ENDPOINT = f"{API_PREFIX}/judge/decide"
API_KEY = "test-virtual-court-key"


def _request_data() -> dict:
    return {
        "state_version": 18,
        "current_stage": "COURT_INVESTIGATION",
        "current_step": "INQUIRY-D-A",
        "trigger": "CLARIFICATION_NEEDED",
        "task": "要求被告明确回答是否核验过商用授权。",
        "current_speaker": "DEFENDANT",
        "allowed_actions": ["REQUEST_CLARIFICATION"],
        "allowed_targets": ["DEFENDANT"],
        "case_context": {
            "cause_of_action": "著作权侵权纠纷",
            "procedure": "民事一审简易程序",
            "summary": "原告主张被告未经许可使用涉案插画。",
        },
    }


def _response() -> JudgeDecisionResponse:
    return JudgeDecisionResponse.model_validate_json(
        json.dumps(
            {
            "state_version": 18,
            "speech": {
                "type": "CLARIFICATION",
                "text": "被告，请明确回答使用前是否核验过商用授权。",
                "target_role": "DEFENDANT",
            },
            "action": {
                "type": "REQUEST_CLARIFICATION",
                "target_role": "DEFENDANT",
            },
            "legal_citations": [],
            "confidence": "HIGH",
            "warnings": [],
            }
        )
    )


class _FakeJudgeService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.requests = []

    async def decide(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return _response()


def _client(service: _FakeJudgeService) -> TestClient:
    app = FastAPI()
    register_integration_exception_handlers(app)
    app.include_router(router, prefix=API_PREFIX)
    app.state.container = SimpleNamespace(judge_service=service)
    return TestClient(app)


def _auth_headers() -> dict[str, str]:
    return {"X-Integration-Key": API_KEY}


def test_judge_api_accepts_key_and_returns_strict_response(monkeypatch):
    monkeypatch.setattr(settings, "virtual_court_api_key", SecretStr(API_KEY))
    service = _FakeJudgeService()

    response = _client(service).post(
        ENDPOINT,
        headers=_auth_headers(),
        json=_request_data(),
    )

    assert response.status_code == 200
    assert response.json()["state_version"] == 18
    assert response.json()["action"]["type"] == "REQUEST_CLARIFICATION"
    assert len(service.requests) == 1


def test_judge_api_rejects_missing_and_wrong_keys(monkeypatch):
    monkeypatch.setattr(settings, "virtual_court_api_key", SecretStr(API_KEY))
    client = _client(_FakeJudgeService())

    for headers in ({}, {"X-Integration-Key": "wrong-key"}):
        response = client.post(ENDPOINT, headers=headers, json=_request_data())
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


def test_judge_api_fails_closed_when_key_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "virtual_court_api_key", SecretStr(""))

    response = _client(_FakeJudgeService()).post(
        ENDPOINT,
        headers=_auth_headers(),
        json=_request_data(),
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_judge_api_maps_request_and_model_validation_errors(monkeypatch):
    monkeypatch.setattr(settings, "virtual_court_api_key", SecretStr(API_KEY))

    invalid_request = _request_data()
    invalid_request.pop("current_step")
    response = _client(_FakeJudgeService()).post(
        ENDPOINT,
        headers=_auth_headers(),
        json=invalid_request,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"

    response = _client(
        _FakeJudgeService(error=JudgeInvalidResponseError())
    ).post(
        ENDPOINT,
        headers=_auth_headers(),
        json=_request_data(),
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MODEL_RESPONSE_INVALID"

@pytest.mark.parametrize(
    ("service_error", "status_code", "error_code", "retryable"),
    [
        (
            JudgeConfigurationError(),
            503,
            "SERVICE_UNAVAILABLE",
            False,
        ),
        (
            JudgeUnavailableError(),
            503,
            "SERVICE_UNAVAILABLE",
            True,
        ),
        (
            JudgeTimeoutError(params={"timeout": 120}),
            504,
            "UPSTREAM_TIMEOUT",
            True,
        ),
        (JudgeServiceError(), 500, "INTERNAL_ERROR", False),
    ],
)
def test_judge_api_maps_service_errors(
    monkeypatch,
    service_error,
    status_code,
    error_code,
    retryable,
):
    monkeypatch.setattr(settings, "virtual_court_api_key", SecretStr(API_KEY))

    response = _client(_FakeJudgeService(error=service_error)).post(
        ENDPOINT,
        headers=_auth_headers(),
        json=_request_data(),
    )

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == error_code
    assert response.json()["error"]["retryable"] is retryable


def test_judge_api_localizes_error_without_exposing_diagnostics(monkeypatch):
    monkeypatch.setattr(settings, "virtual_court_api_key", SecretStr(API_KEY))
    monkeypatch.setattr(
        error_translation,
        "t",
        lambda key, **params: (
            "独任审判员服务暂时不可用"
            if key == "judge.unavailable"
            else key
        ),
    )
    error = JudgeUnavailableError(
        cause=RuntimeError("private provider endpoint and credential detail")
    )

    response = _client(_FakeJudgeService(error=error)).post(
        ENDPOINT,
        headers=_auth_headers(),
        json=_request_data(),
    )

    assert response.status_code == 503
    assert response.json()["error"]["message"] == "独任审判员服务暂时不可用"
    assert "private provider endpoint" not in response.text


def test_openapi_declares_api_key_header(monkeypatch):
    monkeypatch.setattr(settings, "virtual_court_api_key", SecretStr(API_KEY))
    client = _client(_FakeJudgeService())

    schema = client.get("/openapi.json").json()
    operation = schema["paths"][ENDPOINT]["post"]
    security_name = next(iter(operation["security"][0]))
    security_scheme = schema["components"]["securitySchemes"][security_name]

    assert security_scheme["in"] == "header"
    assert security_scheme["name"] == "X-Integration-Key"

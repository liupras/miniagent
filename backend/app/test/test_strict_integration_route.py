"""Shared raw-JSON route behavior used by integration endpoints."""

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.integrations.strict_json_route import (
    REQUEST_MAX_BYTES,
    StrictIntegrationRoute,
)
from app.api.integrations.virtual_court.judge import router as judge_router


def client():
    app = FastAPI()
    router = APIRouter(route_class=StrictIntegrationRoute)

    @router.post("/probe")
    async def probe(body: dict):
        return body

    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_judge_router_uses_the_shared_strict_route():
    assert judge_router.route_class is StrictIntegrationRoute
    assert all(isinstance(route, StrictIntegrationRoute) for route in judge_router.routes)


def test_valid_body_is_replayed_for_fastapi_model_binding():
    response = client().post(
        "/probe",
        content=b'{"value":"accepted"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json() == {"value": "accepted"}


def test_duplicate_fields_are_rejected_before_endpoint_execution():
    response = client().post(
        "/probe",
        content=b'{"value":1,"value":2}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "INVALID_REQUEST",
        "message": "请求必须是合法且没有重复字段的 UTF-8 JSON。",
        "retryable": False,
        "details": {"reason": "invalid_json"},
    }


def test_invalid_utf8_is_rejected_as_invalid_json():
    response = client().post(
        "/probe",
        content=b'{"value":"\xff"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {"reason": "invalid_json"}


def test_body_over_limit_is_rejected_without_parsing():
    response = client().post(
        "/probe",
        content=b" " * (REQUEST_MAX_BYTES + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "INVALID_REQUEST",
        "message": "请求超过大小限制。",
        "retryable": False,
        "details": {"reason": "body_size"},
    }

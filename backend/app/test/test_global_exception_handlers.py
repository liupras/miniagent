from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.exception_handlers import register_global_exception_handlers
from app.schemas.exceptions import AlreadyExistsError, BadRequestError, NotFoundError


def _client() -> TestClient:
    app = FastAPI()
    register_global_exception_handlers(app)

    @app.get("/not-found")
    async def not_found():
        raise NotFoundError("User", 7)

    @app.get("/conflict")
    async def conflict():
        raise AlreadyExistsError("User", 7)

    @app.get("/bad-request")
    async def bad_request():
        raise BadRequestError("Request", "invalid")

    @app.get("/unexpected")
    async def unexpected():
        raise RuntimeError("internal implementation detail")

    @app.get("/api/v1/integrations/unexpected")
    async def integration_unexpected():
        raise RuntimeError("internal integration detail")

    @app.get("/api/v1/integrations/domain-error")
    async def integration_domain_error():
        raise BadRequestError("Integration", "invalid")

    return TestClient(app, raise_server_exceptions=False)


def test_domain_errors_are_mapped_by_fastapi_handlers():
    client = _client()

    not_found = client.get("/not-found")
    conflict = client.get("/conflict")
    bad_request = client.get("/bad-request")

    assert not_found.status_code == 404
    assert not_found.json()["code"] == 404
    assert conflict.status_code == 409
    assert conflict.json()["code"] == 409
    assert bad_request.status_code == 400
    assert bad_request.json()["code"] == 400


def test_unexpected_error_uses_safe_standard_response():
    response = _client().get("/unexpected")

    assert response.status_code == 500
    assert response.json()["code"] == 500
    assert "internal implementation detail" not in response.text


def test_unexpected_integration_error_uses_integration_envelope():
    response = _client().get("/api/v1/integrations/unexpected")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.json()["error"]["retryable"] is False
    assert "internal integration detail" not in response.text


def test_other_domain_errors_keep_the_integration_envelope():
    response = _client().get("/api/v1/integrations/domain-error")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.json()["error"]["retryable"] is False

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.user.agent as agent_api
from app.api.exception_handlers import register_global_exception_handlers
from app.services.workplace_agent import (
    AgentAccessDeniedError,
    AgentSessionNotFoundError,
    SessionTitleInvalidError,
)


class _Service:
    def __init__(self, error):
        self.error = error

    async def invoke(self, **kwargs):
        raise self.error

    async def list_user_messages(self, **kwargs):
        raise self.error

    async def rename_user_session(self, *args):
        raise self.error


def _client(error):
    app = FastAPI()
    register_global_exception_handlers(app)
    app.include_router(agent_api.router)
    app.dependency_overrides[agent_api._get_service] = lambda: _Service(error)
    app.dependency_overrides[agent_api.current_user] = lambda: 1
    return TestClient(app, raise_server_exceptions=False)


def _client_with_service(service):
    app = FastAPI()
    register_global_exception_handlers(app)
    app.include_router(agent_api.router)
    app.dependency_overrides[agent_api._get_service] = lambda: service
    app.dependency_overrides[agent_api.current_user] = lambda: 1
    return TestClient(app, raise_server_exceptions=False)


def test_agent_access_error_is_mapped_to_http_403():
    response = _client(AgentAccessDeniedError(1, 7)).post(
        "/invoke",
        json={"agent_id": 7, "query": "hello"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == 403


def test_missing_user_session_is_mapped_to_http_404():
    response = _client(AgentSessionNotFoundError(11)).get(
        "/sessions/11/messages"
    )

    assert response.status_code == 404
    assert response.json()["code"] == 404


def test_invalid_session_title_is_mapped_to_http_400():
    response = _client(SessionTitleInvalidError()).patch(
        "/sessions/11",
        json={"title": "title"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 400


def test_stream_runtime_failure_returns_safe_terminal_sse_event():
    class _Runner:
        agent_name = "test-agent"

        async def stream(self, **kwargs):
            raise RuntimeError("private provider detail")
            yield  # pragma: no cover - makes this an async generator

    class _StreamService:
        async def prepare_call(self, **kwargs):
            return _Runner(), SimpleNamespace(id=11)

    response = _client_with_service(_StreamService()).post(
        "/stream",
        json={"agent_id": 7, "query": "hello"},
    )

    assert response.status_code == 200
    assert "AGENT_STREAM_FAILED" in response.text
    assert "private provider detail" not in response.text

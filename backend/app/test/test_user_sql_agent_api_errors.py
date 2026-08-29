from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.user.sql_agent as sql_agent_api


class _FailingStreamService:
    async def astream(self, **kwargs):
        raise RuntimeError("private database connection detail")
        yield  # pragma: no cover - makes this an async generator


def test_sql_agent_stream_returns_safe_error_event():
    app = FastAPI()
    app.include_router(sql_agent_api.router)
    app.dependency_overrides[sql_agent_api._get_service] = (
        lambda: _FailingStreamService()
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/chat_stream", params={"query": "total revenue"})

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "SQL_AGENT_STREAM_FAILED" in response.text
    assert "private database connection detail" not in response.text

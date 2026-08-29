import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.operations as operations_api
import app.services.admin.system_status as status_module
from app.api.exception_handlers import register_global_exception_handlers
from app.schemas.exceptions import InfrastructureError
from app.services.admin.system_status import (
    DatabaseInfoUnavailableError,
    SystemStatusService,
)


def test_database_info_service_wraps_database_failure(monkeypatch):
    def fail_inspection(_engine):
        raise RuntimeError("private SQLite connection detail")

    monkeypatch.setattr(status_module, "inspect", fail_inspection)
    service = SystemStatusService(None)

    with pytest.raises(DatabaseInfoUnavailableError) as caught:
        asyncio.run(service.get_database_info())

    assert isinstance(caught.value, InfrastructureError)
    assert isinstance(caught.value.__cause__, RuntimeError)


class _FailingStatusService:
    async def get_database_info(self):
        raise DatabaseInfoUnavailableError(
            cause=RuntimeError("private SQLite connection detail")
        )


def test_database_info_failure_returns_safe_global_error_response():
    app = FastAPI()
    register_global_exception_handlers(app)
    app.include_router(operations_api.router)
    app.dependency_overrides[operations_api._get_system_status_service] = (
        lambda: _FailingStatusService()
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/db/info")

    assert response.status_code == 503
    assert response.json()["code"] == 503
    assert "private SQLite connection detail" not in response.text

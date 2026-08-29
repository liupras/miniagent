from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.admin.sql_agent as sql_agent_api
from app.api.exception_handlers import register_global_exception_handlers
from app.services.sql_agent.exceptions import (
    SQLTableNotFoundError,
    SQLTableOperationError,
    SQLUnsupportedFileTypeError,
)


class _Service:
    def classify_import_file(self, filename):
        raise SQLUnsupportedFileTypeError(filename, ".csv")

    async def get_table_columns(self, schema_name, table_name):
        raise SQLTableNotFoundError(schema_name, table_name)

    async def list_schemas(self):
        raise RuntimeError("private database detail")

    async def list_tables(self, schema_name):
        raise SQLTableOperationError("list_tables")


def _client():
    app = FastAPI()
    register_global_exception_handlers(app)
    app.include_router(sql_agent_api.router)
    service = _Service()
    app.dependency_overrides[sql_agent_api._get_service] = lambda: service
    app.dependency_overrides[sql_agent_api._add] = lambda: 1
    app.dependency_overrides[sql_agent_api._list] = lambda: 1
    app.dependency_overrides[sql_agent_api._delete] = lambda: 1
    return TestClient(app, raise_server_exceptions=False)


def test_unsupported_upload_is_mapped_to_http_415():
    response = _client().post(
        "/import",
        files={"file": ("orders.pdf", b"data", "application/pdf")},
    )

    assert response.status_code == 415
    assert response.json()["code"] == 415


def test_missing_table_is_mapped_to_http_404():
    response = _client().get("/tables/main/missing/columns")

    assert response.status_code == 404
    assert response.json()["code"] == 404


def test_unexpected_failure_reaches_global_handler():
    response = _client().get("/schemas")

    assert response.status_code == 500
    assert response.json()["code"] == 500
    assert "private database detail" not in response.text


def test_duckdb_operation_failure_is_mapped_to_service_unavailable():
    response = _client().get("/tables")

    assert response.status_code == 503
    assert response.json()["code"] == 503

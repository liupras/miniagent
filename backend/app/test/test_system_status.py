import asyncio
from types import SimpleNamespace

from app.api.operations import router
from app.services.admin.system_status import SystemStatusService, _component_status


class _Repository:
    def __init__(self, rows):
        self._rows = rows

    async def get_all_embeddings(self):
        return self._rows

    async def get_all(self):
        return self._rows


def _container(rows=()):
    return SimpleNamespace(embed_db=_Repository(rows), llm_db=_Repository(rows))


def test_operations_routes_are_registered_in_dedicated_router():
    paths = {route.path for route in router.routes}
    assert {"/", "/health", "/config", "/db/info"} <= paths
    assert "/api/v1/admin/system/status" in paths


def test_component_status_handles_partial_and_missing_configuration():
    assert _component_status([]) == "not_configured"
    assert _component_status([{"status": "healthy"}]) == "healthy"
    assert _component_status([{"status": "unhealthy"}]) == "unhealthy"
    assert _component_status([
        {"status": "healthy"}, {"status": "unhealthy"}
    ]) == "degraded"


def test_system_status_aggregates_all_dependencies(monkeypatch):
    service = SystemStatusService(_container())
    healthy = {"status": "healthy", "latency_ms": 1.0}
    monkeypatch.setattr(service, "_check_sqlite", lambda: healthy)
    monkeypatch.setattr(service, "_check_duckdb", lambda: healthy)
    monkeypatch.setattr(service, "_check_vector_db", lambda: healthy)

    async def configured(_loader):
        return {
            "status": "healthy",
            "configured_count": 1,
            "healthy_count": 1,
            "items": [],
        }

    monkeypatch.setattr(service, "_check_configured_services", configured)
    result = asyncio.run(service.get_status())

    assert result["status"] == "healthy"
    assert set(result["components"]) == {
        "api", "sqlite", "duckdb", "vector_db", "embedding", "llm"
    }


def test_model_probe_reports_configured_model(monkeypatch):
    config = SimpleNamespace(
        id=1,
        name="local-qwen",
        provider_name="ollama",
        base_url="http://localhost:11434",
        api_key=None,
        model_name="ollama/qwen3:4b",
    )

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"models": [{"name": "qwen3:4b"}]}

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, headers):
            assert url == "http://localhost:11434/api/tags"
            assert headers == {}
            return _Response()

    monkeypatch.setattr("app.services.admin.system_status.httpx.AsyncClient", _Client)
    result = asyncio.run(SystemStatusService._probe_model(config))
    assert result["status"] == "healthy"
    assert result["model_available"] is True

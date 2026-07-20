import asyncio

from app.api.operations import router
from app.services.admin.system_status import SystemStatusService


def test_operations_routes_are_registered_in_dedicated_router():
    paths = {route.path for route in router.routes}
    assert {"/", "/health", "/config", "/db/info"} <= paths
    assert "/api/v1/admin/system/status" in paths


def test_system_status_aggregates_all_dependencies(monkeypatch):
    service = SystemStatusService(None)
    healthy = {"status": "healthy", "latency_ms": 1.0}
    monkeypatch.setattr(service, "_check_sqlite", lambda: healthy)
    monkeypatch.setattr(service, "_check_duckdb", lambda: healthy)
    monkeypatch.setattr(service, "_collect_resources", lambda: {"cpu": {}})

    result = asyncio.run(service.get_status())

    assert result["status"] == "healthy"
    assert set(result["components"]) == {"api", "sqlite", "duckdb"}
    assert result["resources"] == {"cpu": {}}


def test_resource_snapshot_contains_cpu_memory_disk_and_gpu():
    resources = SystemStatusService._collect_resources()
    assert resources["cpu"]["usage_percent"] >= 0
    assert resources["memory"]["total_bytes"] > 0
    assert resources["disk"]["total_bytes"] > 0
    assert "available" in resources["gpu"]

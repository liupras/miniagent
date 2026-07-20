#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-20
# @description: Runtime health checks used by the administrator system-status endpoint.

from __future__ import annotations

import asyncio
import csv
from datetime import datetime, timezone
import io
import os
import subprocess
from time import perf_counter
from typing import Any

import duckdb
import psutil
from sqlalchemy import text

from app.core.config import settings
from app.infra.db.initializer import db_manager


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 2)


def _error_message(exc: Exception) -> str:
    """Return a concise diagnostic without exposing credentials or tracebacks."""
    return f"{type(exc).__name__}: {exc}"[:500]


class SystemStatusService:
    """Perform lightweight, read-only checks against application dependencies."""

    def __init__(self, _container) -> None:
        # Keep the application container argument for the existing DI factory.
        pass

    async def get_status(self) -> dict[str, Any]:
        started = perf_counter()
        sqlite, duckdb, resources = await asyncio.gather(
            asyncio.to_thread(self._check_sqlite),
            asyncio.to_thread(self._check_duckdb),
            asyncio.to_thread(self._collect_resources),
        )

        components = {
            "api": {"status": "healthy", "message": "API is running"},
            "sqlite": sqlite,
            "duckdb": duckdb,
        }
        statuses = {component["status"] for component in components.values()}
        overall = (
            "healthy"
            if statuses == {"healthy"}
            else "unhealthy"
            if "unhealthy" in statuses
            else "degraded"
        )
        return {
            "status": overall,
            "app_name": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": _elapsed_ms(started),
            "components": components,
            "resources": resources,
        }

    @staticmethod
    def _collect_resources() -> dict[str, Any]:
        """Collect host utilization. GPU metrics are optional and NVIDIA-specific."""
        cpu_started = perf_counter()
        cpu_percent = psutil.cpu_percent(interval=0.1)
        frequency = psutil.cpu_freq()
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage(str(settings.get_sqlite_path()))
        return {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "collection_ms": _elapsed_ms(cpu_started),
            "cpu": {
                "usage_percent": cpu_percent,
                "physical_cores": psutil.cpu_count(logical=False),
                "logical_cores": psutil.cpu_count(logical=True),
                "frequency_mhz": round(frequency.current, 2) if frequency else None,
                "max_frequency_mhz": round(frequency.max, 2) if frequency else None,
            },
            "memory": {
                "total_bytes": memory.total,
                "used_bytes": memory.used,
                "available_bytes": memory.available,
                "usage_percent": memory.percent,
            },
            "swap": {
                "total_bytes": swap.total,
                "used_bytes": swap.used,
                "usage_percent": swap.percent,
            },
            "disk": {
                "total_bytes": disk.total,
                "used_bytes": disk.used,
                "free_bytes": disk.free,
                "usage_percent": disk.percent,
            },
            "gpu": SystemStatusService._collect_nvidia_gpu(),
        }

    @staticmethod
    def _collect_nvidia_gpu() -> dict[str, Any]:
        fields = [
            "name",
            "utilization.gpu",
            "memory.total",
            "memory.used",
            "temperature.gpu",
            "driver_version",
        ]
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    f"--query-gpu={','.join(fields)}",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                check=True,
                text=True,
                timeout=2,
                creationflags=creation_flags,
            )
            devices = []
            for row in csv.reader(io.StringIO(result.stdout)):
                if len(row) != len(fields):
                    continue
                values = [value.strip() for value in row]
                devices.append({
                    "name": values[0],
                    "usage_percent": float(values[1]),
                    "memory_total_bytes": int(float(values[2]) * 1024 * 1024),
                    "memory_used_bytes": int(float(values[3]) * 1024 * 1024),
                    "temperature_celsius": float(values[4]),
                    "driver_version": values[5],
                })
            return {"available": bool(devices), "devices": devices}
        except (FileNotFoundError, subprocess.SubprocessError, ValueError) as exc:
            return {
                "available": False,
                "devices": [],
                "message": _error_message(exc),
            }

    @staticmethod
    def _check_sqlite() -> dict[str, Any]:
        started = perf_counter()
        try:
            with db_manager.engine.connect() as connection:
                connection.execute(text("SELECT 1")).scalar_one()
            return {
                "status": "healthy",
                "latency_ms": _elapsed_ms(started),
                "path": str(settings.get_sqlite_path() / "miniagent.db"),
            }
        except Exception as exc:
            return {
                "status": "unhealthy",
                "latency_ms": _elapsed_ms(started),
                "message": _error_message(exc),
            }

    @staticmethod
    def _check_duckdb() -> dict[str, Any]:
        started = perf_counter()
        connection = None
        try:
            connection = duckdb.connect(str(settings.get_duck_db_path() / "duckdb.db"))
            result = connection.execute("SELECT 1").fetchall()
            if not result or result[0][0] != 1:
                raise RuntimeError("Unexpected SELECT 1 result")
            return {
                "status": "healthy",
                "latency_ms": _elapsed_ms(started),
                "path": str(settings.get_duck_db_path() / "duckdb.db"),
            }
        except Exception as exc:
            return {
                "status": "unhealthy",
                "latency_ms": _elapsed_ms(started),
                "message": _error_message(exc),
            }
        finally:
            if connection is not None:
                connection.close()

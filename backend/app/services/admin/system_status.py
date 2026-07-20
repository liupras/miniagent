#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-20
# @description: Runtime health checks used by the administrator system-status endpoint.

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Awaitable, Callable, Iterable

import chromadb
import duckdb
import httpx
from sqlalchemy import text

from app.core.config import settings
from app.infra.db.initializer import db_manager


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 2)


def _error_message(exc: Exception) -> str:
    """Return a concise diagnostic without exposing credentials or tracebacks."""
    return f"{type(exc).__name__}: {exc}"[:500]


def _component_status(items: list[dict[str, Any]]) -> str:
    if not items:
        return "not_configured"
    healthy = sum(item["status"] == "healthy" for item in items)
    if healthy == len(items):
        return "healthy"
    if healthy:
        return "degraded"
    return "unhealthy"


class SystemStatusService:
    """Perform lightweight, read-only checks against application dependencies."""

    def __init__(self, container) -> None:
        self._embedding_db = container.embed_db
        self._llm_db = container.llm_db

    async def get_status(self) -> dict[str, Any]:
        started = perf_counter()
        sqlite, duckdb, vector_db, embedding, llm = await asyncio.gather(
            asyncio.to_thread(self._check_sqlite),
            asyncio.to_thread(self._check_duckdb),
            asyncio.to_thread(self._check_vector_db),
            self._check_configured_services(self._embedding_db.get_all_embeddings),
            self._check_configured_services(self._llm_db.get_all),
        )

        components = {
            "api": {"status": "healthy", "message": "API is running"},
            "sqlite": sqlite,
            "duckdb": duckdb,
            "vector_db": vector_db,
            "embedding": embedding,
            "llm": llm,
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

    @staticmethod
    def _check_vector_db() -> dict[str, Any]:
        started = perf_counter()
        try:
            client = chromadb.PersistentClient(path=str(settings.get_vector_db_path()))
            heartbeat = client.heartbeat()
            collections = client.list_collections()
            return {
                "status": "healthy",
                "latency_ms": _elapsed_ms(started),
                "path": str(settings.get_vector_db_path()),
                "heartbeat": heartbeat,
                "collection_count": len(collections),
            }
        except Exception as exc:
            return {
                "status": "unhealthy",
                "latency_ms": _elapsed_ms(started),
                "message": _error_message(exc),
            }

    async def _check_configured_services(
        self,
        loader: Callable[[], Awaitable[Iterable[Any]]],
    ) -> dict[str, Any]:
        started = perf_counter()
        try:
            configs = list(await loader())
        except Exception as exc:
            return {
                "status": "unhealthy",
                "latency_ms": _elapsed_ms(started),
                "configured_count": 0,
                "message": _error_message(exc),
                "items": [],
            }

        items = await asyncio.gather(*(self._probe_model(config) for config in configs))
        return {
            "status": _component_status(items),
            "latency_ms": _elapsed_ms(started),
            "configured_count": len(items),
            "healthy_count": sum(item["status"] == "healthy" for item in items),
            "items": items,
        }

    @staticmethod
    async def _probe_model(config: Any) -> dict[str, Any]:
        started = perf_counter()
        provider = (config.provider_name or "").lower()
        base_url = (config.base_url or "").rstrip("/")
        model_name = config.model_name
        item = {
            "id": config.id,
            "name": config.name,
            "provider": config.provider_name,
            "model": model_name,
        }
        if not base_url:
            return {
                **item,
                "status": "unhealthy",
                "latency_ms": _elapsed_ms(started),
                "message": "Missing base URL",
            }

        is_ollama = provider == "ollama" or model_name.startswith("ollama/")
        ollama_base_url = base_url.removesuffix("/v1")
        url = (
            f"{ollama_base_url}/api/tags" if is_ollama else f"{base_url}/models"
        )
        headers = {}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()

            if is_ollama:
                available = {
                    value
                    for model in payload.get("models", [])
                    for value in (model.get("name"), model.get("model"))
                    if value
                }
                expected = model_name.removeprefix("ollama/")
            else:
                available = {
                    model.get("id") for model in payload.get("data", []) if model.get("id")
                }
                expected = model_name.split("/", 1)[-1]

            model_available = expected in available
            return {
                **item,
                "status": "healthy" if model_available else "unhealthy",
                "latency_ms": _elapsed_ms(started),
                "model_available": model_available,
                **({} if model_available else {"message": "Configured model was not found"}),
            }
        except Exception as exc:
            return {
                **item,
                "status": "unhealthy",
                "latency_ms": _elapsed_ms(started),
                "model_available": False,
                "message": _error_message(exc),
            }

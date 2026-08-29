#!/usr/bin/python
# -*- coding:utf-8 -*-

import asyncio
from types import SimpleNamespace

from app.repositories.async_domain import AsyncDomainDatabase
from app.services.admin.domain import DomainService


class _DomainRepository:
    def __init__(self) -> None:
        self.created: list[dict] = []

    async def get_by_name(self, name: str):
        if name == "existing":
            return SimpleNamespace(id=1, name=name)
        if name == "broken":
            raise RuntimeError("database rejected row")
        return None

    async def create(self, payload: dict):
        if "name" not in payload:
            raise TypeError("name is required")
        self.created.append(payload)
        return SimpleNamespace(id=len(self.created), **payload)


class _CacheInvalidator:
    def __init__(self) -> None:
        self.domain_change_count = 0

    def on_domain_changed(self) -> None:
        self.domain_change_count += 1


def test_repository_no_longer_owns_best_effort_bulk_import():
    assert not hasattr(AsyncDomainDatabase, "bulk_upsert")


def test_service_owns_per_record_bulk_import_tolerance():
    repository = _DomainRepository()
    cache = _CacheInvalidator()
    container = SimpleNamespace(
        domain_db=repository,
        object_cache_invalidator=cache,
    )
    service = DomainService(container)

    result = asyncio.run(
        service.bulk_upsert(
            [
                {"name": "created", "description": "new"},
                {"name": "existing"},
                {"name": "broken"},
                {"description": "missing name"},
            ]
        )
    )

    assert result[:2] == (1, 1)
    assert result[2] == [
        "broken: database rejected row",
        "<unknown>: name is required",
    ]
    assert repository.created == [
        {"name": "created", "description": "new"},
    ]
    assert cache.domain_change_count == 1

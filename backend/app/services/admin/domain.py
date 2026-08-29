#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-05
# @description: Domain service — business / orchestration layer

from __future__ import annotations

from app.core.logger_config import get_logger

logger = get_logger(__name__)
from typing import  Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.service_container import ServiceContainer

from app.schemas.admin.domain import (
    DomainCreate,
    DomainListResponse,
    DomainRead,
    DomainUpdate,
    DomainOption
)

from app.schemas.exceptions import AlreadyExistsError, NotFoundError

class DomainNotFoundError(NotFoundError):
    def __init__(self, entity_id: Any):
        super().__init__("Domain", entity_id)

class DomainAlreadyExistsError(AlreadyExistsError):
    def __init__(self, entity_id: Any):
        super().__init__("Domain", entity_id)

class DomainService:

    def __init__(self, container:ServiceContainer) -> None:
        self._repo = container.domain_db
        self._cache = container.object_cache_invalidator

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_domain_options(self) -> List[DomainOption]:
        """Get domain options for dropdown selection."""
        domains = await self._repo.get_all_domains()
        return [DomainOption.model_validate(domain) for domain in domains]

    async def get_domain(self, domain_id: int) -> DomainRead:
        domain = await self._repo.get_by_id(domain_id)
        if domain is None:
            raise DomainAlreadyExistsError(domain_id)
        return DomainRead.model_validate(domain)

    async def list_domains(
        self,
        *,
        type_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> DomainListResponse:
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 20

        items, total = await self._repo.list_domains(
            type_filter=type_filter,
            page=page,
            page_size=page_size,
        )
        return DomainListResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=[DomainRead.model_validate(d) for d in items],
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create_domain(self, payload: DomainCreate) -> DomainRead:
        # Duplicate-name check with a meaningful error message
        existing = await self._repo.get_by_name(payload.name)
        if existing:
            raise DomainAlreadyExistsError(existing.id)
        domain = await self._repo.create(payload.model_dump(exclude_unset=True))
        logger.info("Created domain '{}' (id={})", domain.name, domain.id)
        return DomainRead.model_validate(domain)

    async def update_domain(self, domain_id: int, payload: DomainUpdate) -> DomainRead:
        # If renaming, ensure the new name is not taken by another domain
        if payload.name:
            conflict = await self._repo.get_by_name(payload.name)
            if conflict and conflict.id != domain_id:
                raise DomainAlreadyExistsError(conflict.id)

        domain = await self._repo.update(domain_id, payload.model_dump(exclude_unset=True))
        if domain is None:
            raise DomainNotFoundError(domain_id)
        logger.info("Updated domain id={}", domain_id)
        self._cache.on_domain_changed()
        return DomainRead.model_validate(domain)

    async def delete_domain(self, domain_id: int) -> None:
        deleted = await self._repo.delete(domain_id)
        if not deleted:
            raise DomainNotFoundError(domain_id)
        self._cache.on_domain_changed()
        logger.info("Deleted domain id={}", domain_id)

    async def bulk_delete(self, ids: list[int]) -> int:
        count = await self._repo.bulk_delete(ids)
        self._cache.on_domain_changed()
        return count

    async def bulk_upsert(
        self,
        payloads: List[dict],
    ) -> tuple[int, int, List[str]]:
        """Best-effort domain import with per-record failure isolation.

        Each repository call owns its transaction. Database failures are
        therefore rolled back and re-raised by the repository session boundary
        before this import workflow records the failed item and continues.
        """
        inserted = skipped = 0
        errors: List[str] = []

        for payload in payloads:
            domain_name = str(payload.get("name") or "<unknown>")
            try:
                existing = await self._repo.get_by_name(domain_name)
                if existing:
                    skipped += 1
                    continue

                await self._repo.create(payload)
                inserted += 1
            except Exception as exc:
                # Per-item isolation is intentional for this best-effort import
                # workflow. Repository methods have already rolled back their
                # failed transaction before control reaches this point.
                logger.exception(
                    "Failed to import domain '{}'",
                    domain_name,
                )
                errors.append(f"{domain_name}: {exc}")

        if inserted:
            self._cache.on_domain_changed()
        return inserted, skipped, errors

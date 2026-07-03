#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-05
# @description: Domain service — business / orchestration layer

from __future__ import annotations

from loguru import logger
from typing import  Any, List, Optional

from app.repositories.async_domain import AsyncDomainDatabase
from app.schemas.admin.domain import (
    DomainCreate,
    DomainListResponse,
    DomainRead,
    DomainUpdate,
    DomainOption
)

from app.schemas.common import AlreadyExistsError, NotFoundError

class DomainNotFoundError(NotFoundError):
    def __init__(self, entity_id: Any):
        super().__init__("Domain", entity_id)

class DomainAlreadyExistsError(AlreadyExistsError):
    def __init__(self, entity_id: Any):
        super().__init__("Domain", entity_id)

class DomainService:

    def __init__(self, repo: AsyncDomainDatabase) -> None:
        self._repo = repo

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
        return DomainRead.model_validate(domain)

    async def delete_domain(self, domain_id: int) -> None:
        deleted = await self._repo.delete(domain_id)
        if not deleted:
            raise DomainNotFoundError(domain_id)
        logger.info("Deleted domain id={}", domain_id)

    async def bulk_delete(self, ids: list[int]) -> int:
        count = await self._repo.bulk_delete(ids)
        return count

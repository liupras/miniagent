#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: Domain Database Management (Asynchronous Version)

from typing import List, Optional

from loguru import logger
from sqlalchemy import delete, func, select

from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import Domain, KnowledgeBase

class AsyncDomainDatabase(AsyncBaseDatabase):
    """Domain table operations - Asynchronous Version"""

    # ── Queries ───────────────────────────────────────────────────────────

    async def get_by_id(self, domain_id: int) -> Optional[Domain]:
        """Return the Domain row for *domain_id*, or None if not found."""
        async with self.get_session() as session:
            domain = await session.get(Domain, domain_id)
        
        if domain is None:
            logger.warning(f"[DB] Domain not found: domain_id={domain_id}")
        return domain

    async def get_by_name(self, name: str) -> Optional[Domain]:
        """
        Return the Domain row for *name*, or None if not found.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(Domain).where(Domain.name == name)
            )
            domain = result.scalar_one_or_none()
            
        if domain is None:
            logger.warning(f"[DB] Domain not found: name='{name}'")
        return domain

    async def get_domain_by_kb_id(self, kb_id: int) -> Optional[Domain]:
        """
        Return the Domain that the given KnowledgeBase belongs to via JOIN.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(Domain)
                .join(KnowledgeBase, KnowledgeBase.domain_id == Domain.id)
                .where(KnowledgeBase.id == kb_id)
            )
            domain = result.scalar_one_or_none()
            
        if domain is None:
            logger.warning(
                f"[DB] get_domain_by_kb_id: no Domain found for kb_id={kb_id}"
            )
        else:
            logger.debug(
                f"[DB] get_domain_by_kb_id: kb_id={kb_id} "
                f"domain='{domain.name}' id={domain.id}"
            )
        return domain

    async def get_all_domains(self) -> List[Domain]:
        """
        Return all Domain rows ordered by name.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(Domain).order_by(Domain.name)
            )
            domains = result.scalars().all()
            
        logger.debug(f"[DB] get_all_domains: found={len(domains)}")
        return list(domains)

    async def domain_exists(self, name: str) -> bool:
        """Return True when a Domain row with *name* exists."""
        domain = await self.get_by_name(name)
        return domain is not None
    
    async def list_domains(
        self,
        *,
        type_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[Domain], int]:
        """
        Return (items, total) with optional type filter and pagination.

        Args:
            type_filter: If given, restrict to domains whose ``type`` matches.
            page:        1-based page number.
            page_size:   Number of records per page.

        Returns:
            A tuple of (list of Domain ORM objects, total matching count).
        """
        async with self.get_session() as session:
            query = select(Domain)
            if type_filter:
                query = query.where(Domain.type == type_filter)

            # Total count (re-use same filter)
            count_query = select(func.count()).select_from(query.subquery())
            total: int = (await session.execute(count_query)).scalar_one()

            # Paginated results — deterministic ordering by PK
            offset = (page - 1) * page_size
            rows = (
                await session.execute(
                    query.order_by(Domain.id).offset(offset).limit(page_size)
                )
            ).scalars().all()

            return list(rows), total

    # ── Mutations ─────────────────────────────────────────────────────────

    async def create(self, payload: dict) -> Domain:
        """
        Insert a new Domain row.

        Raises:
            ValueError: if a domain with the same name already exists.
        """
        async with self.get_session() as session:
            domain = Domain(**payload)
            session.add(domain)
            logger.info(f"[DB] Domain created: name='{domain.name}' id={domain.id}")
            return domain

    async def update(self, domain_id: int, payload: dict) -> Optional[Domain]:
        async with self.get_session() as session:
            stmt = select(Domain).where(Domain.id == domain_id)
            result = await session.execute(stmt)
            domain = result.scalar_one_or_none()

            if not domain:
                return None
            for field, value in payload.items():
                setattr(domain, field, value)
            logger.info(f"[DB] Domain updated: domain_id={domain_id}")
            return domain
  
    async def delete(self, domain_id: int) -> int:  
        async with self.get_session() as session:
            result = await session.execute(
                delete(Domain).where(Domain.id == domain_id)
            )
            return result.rowcount

        logger.info(f"[DB] Domain deleted: domain_id={domain_id}")
        return True
    
    async def bulk_delete(
        self, ids: list[int]
    ) -> int:
        
        async with self.get_session() as session:
            deleted = 0
            for id in ids:
                obj = await self.get_by_id(id)
                if obj is not None:
                    await session.delete(obj)
                    deleted += 1
            return deleted
        

    async def bulk_upsert(
        self, payloads: List[dict]
    ) -> tuple[int, int, List[str]]:
        """
        Insert each item only if its name does not yet exist (insert-or-skip).

        Returns:
            (inserted_count, skipped_count, error_messages)
        """
        inserted = skipped = 0
        errors: List[str] = []

        for payload in payloads:
            try:
                existing = await self.get_by_name(payload["name"])
                if existing:
                    skipped += 1
                    continue
                await self.create(payload)
                inserted += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{payload["name"]}: {exc}")

        return inserted, skipped, errors
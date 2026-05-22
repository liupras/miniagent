#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: Domain Database Management (Asynchronous Version)

from typing import List, Optional

from loguru import logger
from sqlalchemy import select

from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import Domain, KnowledgeBase

class AsyncDomainDatabase(AsyncBaseDatabase):
    """Domain table operations - Asynchronous Version"""

    # ── Queries ───────────────────────────────────────────────────────────

    async def get_domain(self, domain_id: int) -> Optional[Domain]:
        """Return the Domain row for *domain_id*, or None if not found."""
        async with self.get_session() as session:
            domain = await session.get(Domain, domain_id)
        
        if domain is None:
            logger.warning(f"[DB] Domain not found: domain_id={domain_id}")
        return domain

    async def get_domain_by_name(self, name: str) -> Optional[Domain]:
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
        domain = await self.get_domain_by_name(name)
        return domain is not None

    # ── Mutations ─────────────────────────────────────────────────────────

    async def create_domain(
        self,
        name: str,
        description: Optional[str] = None,
        metadata_schema: Optional[dict] = None,
    ) -> Domain:
        """
        Insert a new Domain row and return it.
        """

        if await self.domain_exists(name):
            raise ValueError(f"Domain '{name}' already exists")

        domain = Domain(
            name            = name,
            description     = description,
            metadata_schema = metadata_schema,
        )
        
        async with self.get_session() as session:
            session.add(domain)
            # flush ensures ID generation and allows refresh.
            await session.flush()
            await session.refresh(domain)

        logger.info(f"[DB] Domain created: name='{name}' id={domain.id}")
        return domain

    async def update_domain(
        self,
        domain_id: int,
        description: Optional[str] = None,
        metadata_schema: Optional[dict] = None,
    ) -> Optional[Domain]:
        """
        Update mutable fields of a Domain row.
        """
        async with self.get_session() as session:
            domain = await session.get(Domain, domain_id)
            if domain is None:
                logger.warning(
                    f"[DB] update_domain: Domain not found domain_id={domain_id}"
                )
                return None

            if description is not None:
                domain.description = description
            if metadata_schema is not None:
                domain.metadata_schema = metadata_schema

            await session.flush()
            await session.refresh(domain)

        logger.info(f"[DB] Domain updated: domain_id={domain_id}")
        return domain

    async def delete_domain(self, domain_id: int) -> bool:
        """
        Delete a Domain row.
        """
        async with self.get_session() as session:
            domain = await session.get(Domain, domain_id)
            if domain is None:
                logger.warning(
                    f"[DB] delete_domain: Domain not found domain_id={domain_id}"
                )
                return False
            
            await session.delete(domain)

        logger.info(f"[DB] Domain deleted: domain_id={domain_id}")
        return True
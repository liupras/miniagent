#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: EmbeddingDatabase — ORM access layer for the Embedding table.

from typing import Any, List, Optional, Sequence
from sqlalchemy import func, select, delete, distinct
from ..infra.db.database import Embedding
from ..infra.db.async_base import AsyncBaseDatabase

class AsyncEmbeddingDatabase(AsyncBaseDatabase):

    # =========================================================================
    # Create
    # =========================================================================

    async def create(
        self,
        name:          str,
        provider_name: str,
        base_url:      str,
        model_name:    str,
        api_key:       Optional[str] = None,
        max_input_tokens: int        = 512,
    ) -> Embedding:
        embedding = Embedding(
            name=name,
            provider_name=provider_name,
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            max_input_tokens=max_input_tokens,
        )
        async with self.get_session() as s:
            s.add(embedding)
            await s.flush()
            await s.refresh(embedding)
            return embedding

    # =========================================================================
    # Read
    # =========================================================================

    async def get_by_id(self, embedding_id: int) -> Optional[Embedding]:
        """Return the Embedding row for *embedding_id*, or None if not found."""
        async with self.get_session() as session:
            embedding = await session.get(Embedding, embedding_id)
            return embedding

    async def get_by_name(self, name: str) -> Optional[Embedding]:
        async with self.get_session() as s:
            result = await s.execute(
                select(Embedding).where(Embedding.name == name)
            )
            return result.scalar_one_or_none()
        
    async def get_all_embeddings(self) -> List[Embedding]:
        """
        Return all Embedding rows ordered by name.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(Embedding).order_by(Embedding.name)
            )
            embeddings = result.scalars().all()         
            return list(embeddings)

    async def embedding_exists(self, name: str) -> bool:
        """Return True when an Embedding row with *name* exists."""
        embedding = await self.get_by_name(name)
        return embedding is not None

    async def get_by_provider_and_model(
        self, provider_name: str, model_name: str
    ) -> Optional[Embedding]:
        async with self.get_session() as s:
            stmt = select(Embedding).filter(
                Embedding.provider_name == provider_name,
                Embedding.model_name    == model_name
            )
            result = await s.execute(stmt)
            return result.scalars().first()

    async def list_all(self) -> Sequence[Embedding]:
        async with self.get_session() as s:
            stmt = select(Embedding).order_by(Embedding.provider_name, Embedding.model_name)
            result = await s.execute(stmt)
            return result.scalars().all()

    async def get_provider_names(self) -> list[str]:
        async with self.get_session() as s:
            stmt = select(distinct(Embedding.provider_name)).order_by(Embedding.provider_name)
            result = await s.execute(stmt)
            return [r for r in result.scalars()]

    async def list_embeddings(
        self,
        *,
        name: Optional[str] = None,
        provider_name: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[Embedding], int]:
        """
        Return (items, total) with optional filters and pagination.
        """
        async with self.get_session() as session:
            query = select(Embedding)
            if name:
                query = query.where(Embedding.name == name)
            if provider_name:
                query = query.where(Embedding.provider_name == provider_name)

            # Total count (re-use same filter)
            count_query = select(func.count()).select_from(query.subquery())
            total: int = (await session.execute(count_query)).scalar_one()

            # Paginated results — deterministic ordering by PK
            offset = (page - 1) * page_size
            rows = (
                await session.execute(
                    query.order_by(Embedding.id).offset(offset).limit(page_size)
                )
            ).scalars().all()

            return list(rows), total

    # =========================================================================
    # Update
    # =========================================================================

    async def update(
        self,
        embedding_id: int,
        **fields: Any,
    ) -> Optional[Embedding]:
        allowed = {
            "name",
            "provider_name",
            "base_url",
            "api_key",
            "model_name",
            "max_input_tokens",
        }
        invalid = set(fields) - allowed
        if invalid:
            raise ValueError(f"Invalid field(s) for Embedding.update: {invalid}")

        async with self.get_session() as s:
            embedding = await s.get(Embedding, embedding_id)
            if not embedding:
                return None

            for key, value in fields.items():
                setattr(embedding, key, value)

            return embedding

    # =========================================================================
    # Delete
    # =========================================================================

    async def delete(self, embedding_id: int) -> bool:
        async with self.get_session() as s:
            embedding = await s.get(Embedding, embedding_id)
            if not embedding:
                return False
            await s.delete(embedding)
            return True

    async def delete_by_provider(self, provider_name: str) -> int:
        async with self.get_session() as s:
            stmt = delete(Embedding).where(Embedding.provider_name == provider_name)
            result = await s.execute(stmt)
            return result.rowcount

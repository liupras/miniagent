#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: EmbeddingDatabase — ORM access layer for the Embedding table.

from typing import Optional, Sequence
from sqlalchemy import select, delete, distinct
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
        max_tokens:    int           = 512,
    ) -> Embedding:
        embedding = Embedding(
            name=name,
            provider_name=provider_name,
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            max_tokens=max_tokens,
        )
        async with self.get_session() as s:
            s.add(embedding)
            await s.flush()
            await s.refresh(embedding)
            return embedding

    # =========================================================================
    # Read
    # =========================================================================

    async def get_by_name(self, name: str) -> Optional[Embedding]:
        async with self.get_session() as s:
            return await s.get(Embedding, name)

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

    async def exists(self, name: str) -> bool:
        async with self.get_session() as s:
            stmt = select(Embedding).where(Embedding.name == name)
            result = await s.execute(stmt)
            return result.scalars().first() is not None

    # =========================================================================
    # Update
    # =========================================================================

    async def update(
        self,
        name:          str,
        **kwargs  # Simplify the update logic for a large number of optional parameters using kwargs.
    ) -> Optional[Embedding]:
        async with self.get_session() as s:
            embedding = await s.get(Embedding, name)
            if not embedding:
                return None
            
            for key, value in kwargs.items():
                if value is not None:
                    setattr(embedding, key, value)
            
            await s.flush()
            await s.refresh(embedding)
            return embedding

    # =========================================================================
    # Delete
    # =========================================================================

    async def delete(self, name: str) -> bool:
        async with self.get_session() as s:
            embedding = await s.get(Embedding, name)
            if not embedding:
                return False
            await s.delete(embedding)
            return True

    async def delete_by_provider(self, provider_name: str) -> int:
        async with self.get_session() as s:
            stmt = delete(Embedding).where(Embedding.provider_name == provider_name)
            result = await s.execute(stmt)
            return result.rowcount
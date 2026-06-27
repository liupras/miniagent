#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-14
# @description: Embedding Service Layer – Business logic

from typing import Any, List, Tuple, Optional

from app.schemas.admin.embedding import (
    EmbeddingCreate,
    EmbeddingRead,
    EmbeddingUpdate,
    EmbeddingOption
)
from app.repositories.async_embedding import AsyncEmbeddingDatabase
from app.schemas.common import NotFoundError,AlreadyExists

class EmbeddingNotFoundError(NotFoundError):
    def __init__(self, entity_id: Any):
        super().__init__("Embedding", entity_id)

class EmbeddingAlreadyExistsError(AlreadyExists):
    def __init__(self, entity_id: Any):
        super().__init__("Embedding", entity_id)

class EmbeddingService:
    def __init__(self, db:AsyncEmbeddingDatabase):
        self._db = db

    async def list_embeddings(
        self,
        *,
        name: Optional[str] = None,
        provider_name: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[EmbeddingRead], int]:
        """List embeddings with optional filtering and pagination."""
        items, total = await self._db.list_embeddings(
            name=name,
            provider_name=provider_name,
            page=page,
            page_size=page_size
        )
        return [EmbeddingRead.model_validate(item) for item in items], total

    async def get_by_id(self, embedding_id: int) -> Optional[EmbeddingRead]:
        """Get a single embedding by ID."""
        embedding = await self._db.get_by_id(embedding_id)
        if embedding is None:
            raise EmbeddingNotFoundError(embedding_id)
        return EmbeddingRead.model_validate(embedding)

    async def create(self, payload: EmbeddingCreate) -> EmbeddingRead:
        """Create a new embedding."""
        data = payload.model_dump()
        embedding = await self._db.create(data)
        return EmbeddingRead.model_validate(embedding)

    async def update(self, embedding_id: int, payload: EmbeddingUpdate) -> Optional[EmbeddingRead]:
        """Update an embedding."""
        data = payload.model_dump(exclude_unset=True)
        embedding = await self._db.update(embedding_id, data)
        if embedding is None:
            raise EmbeddingNotFoundError(embedding_id)
        return EmbeddingRead.model_validate(embedding)

    async def delete(self, embedding_id: int) -> int:
        """Delete an embedding."""
        rowcount = await self._db.delete(embedding_id)
        return rowcount

    async def get_embedding_options(self) -> List[EmbeddingOption]:
        """Get embedding options for dropdown selection."""
        embeddings = await self._db.get_all_embeddings()
        return [EmbeddingOption.model_validate(embedding) for embedding in embeddings]
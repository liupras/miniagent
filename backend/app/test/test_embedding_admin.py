import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infra.db.database import Embedding, KnowledgeBase
from app.repositories.async_embedding import AsyncEmbeddingDatabase
from app.schemas.admin.embedding import EmbeddingCreate, EmbeddingUpdate
from app.services.admin.embedding import (
    EmbeddingAlreadyExistsError,
    EmbeddingNotFoundError,
    EmbeddingService,
)


class _CacheInvalidatorSpy:
    def __init__(self) -> None:
        self.embedding_changes = 0

    def on_embedding_changed(self) -> None:
        self.embedding_changes += 1


class _ContainerStub:
    def __init__(self, database, cache) -> None:
        self.embed_db = database
        self.object_cache_invalidator = cache


def test_embedding_management_crud_uses_max_input_tokens():
    asyncio.run(_exercise_embedding_management_crud())


def test_embedding_token_limit_must_be_positive():
    with pytest.raises(ValueError):
        EmbeddingCreate(
            name="invalid",
            provider_name="ollama",
            base_url="http://localhost:11434",
            model_name="bge-large-zh-v1.5",
            max_input_tokens=0,
        )


async def _exercise_embedding_management_crud():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Embedding.__table__.create)
        await connection.run_sync(KnowledgeBase.__table__.create)

    cache = _CacheInvalidatorSpy()
    database = AsyncEmbeddingDatabase(engine, session_factory)
    service = EmbeddingService(_ContainerStub(database, cache))

    created = await service.create(
        EmbeddingCreate(
            name="bge-zh",
            provider_name="ollama",
            base_url="http://localhost:11434",
            api_key="secret",
            model_name="quentinz/bge-large-zh-v1.5",
            max_input_tokens=512,
        )
    )
    assert created.max_input_tokens == 512

    with pytest.raises(EmbeddingAlreadyExistsError):
        await service.create(
            EmbeddingCreate(
                name="bge-zh",
                provider_name="ollama",
                base_url="http://localhost:11434",
                model_name="another-model",
                max_input_tokens=256,
            )
        )

    updated = await service.update(
        created.id,
        EmbeddingUpdate(max_input_tokens=480, api_key=None),
    )
    assert updated.max_input_tokens == 480
    assert updated.api_key is None

    assert await service.delete(created.id) == 1
    with pytest.raises(EmbeddingNotFoundError):
        await service.get_by_id(created.id)

    assert cache.embedding_changes == 3
    await engine.dispose()

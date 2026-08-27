import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from app.retrieval.embedding_inputs import (
    EmbeddingInputGuard,
    EmbeddingInputTooLongError,
)
from app.retrieval.vector_store import VectorStoreManager
from app.runtime.vector_registry import VectorStoreRegistry
from app.services.kb.smart_router import SmartRouter
from app.services.kb.small_to_big_base import ChunkConfig, SmallToBigProcessor
from app.utils.tokens import TokenCounter


class _SizeLimitedEmbedding:
    def __init__(self, maximum_batch_size: int) -> None:
        self.maximum_batch_size = maximum_batch_size
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if len(texts) > self.maximum_batch_size:
            raise RuntimeError("batch too large")
        return [[float(text)] for text in texts]


class _AlwaysFailingEmbedding:
    def __init__(self) -> None:
        self.call_sizes: list[int] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.call_sizes.append(len(texts))
        raise RuntimeError("embedding unavailable")


class _CollectionSpy:
    def __init__(self) -> None:
        self.add_calls: list[dict] = []

    def add(self, **kwargs) -> None:
        self.add_calls.append(kwargs)

    def query(self, **_kwargs) -> dict:
        return {
            "ids": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }


class _QueryEmbedding:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [1.0]


def _lightweight_guard(max_input_tokens: int) -> EmbeddingInputGuard:
    return EmbeddingInputGuard(
        max_input_tokens=max_input_tokens,
        safety_ratio=1,
        token_counter=TokenCounter(enable_exact_near_limit=False),
    )


def test_embedding_input_guard_splits_and_truncates_oversized_text():
    guard = _lightweight_guard(20)
    text = "测" * 45

    pieces = guard.split_text(text)

    assert len(pieces) == 3
    assert "".join(pieces) == text
    assert all(guard.fits(piece) for piece in pieces)
    assert guard.truncate_text(text) == pieces[0]


def test_small_to_big_refines_children_before_chunk_creation():
    guard = _lightweight_guard(20)
    config = ChunkConfig(
        parent_chunk_size=1000,
        parent_overlap=0,
        child_chunk_size=1000,
        child_overlap=0,
        max_input_tokens=20,
    )

    _, children = SmallToBigProcessor().process(
        [Document(page_content="测" * 45, metadata={"source": "plain.txt"})],
        kb_id=1,
        doc_id=2,
        config=config,
    )

    assert len(children) == 3
    assert "".join(child.text for child in children) == "测" * 45
    assert all(guard.fits(child.text) for child in children)
    assert [child.chunk_index for child in children] == [0, 1, 2]


def test_embedding_batch_failure_halves_request_size_and_preserves_order():
    manager = object.__new__(VectorStoreManager)
    manager.embedding = _SizeLimitedEmbedding(maximum_batch_size=2)
    texts = [str(index) for index in range(8)]

    vectors = manager._embed_documents_with_retry(texts, initial_batch_size=8)

    assert [len(call) for call in manager.embedding.calls] == [8, 4, 2, 2, 2, 2]
    assert vectors == [[float(index)] for index in range(8)]


def test_embedding_batch_re_raises_when_one_input_still_fails():
    manager = object.__new__(VectorStoreManager)
    manager.embedding = _AlwaysFailingEmbedding()

    with pytest.raises(RuntimeError, match="embedding unavailable"):
        manager._embed_documents_with_retry(
            [str(index) for index in range(4)],
            initial_batch_size=4,
        )

    assert manager.embedding.call_sizes == [4, 2, 1]


def test_add_chunks_writes_once_after_retry_completes():
    manager = object.__new__(VectorStoreManager)
    manager.embedding = _SizeLimitedEmbedding(maximum_batch_size=2)
    manager.embedding_input_guard = _lightweight_guard(20)
    collection = _CollectionSpy()
    store = SimpleNamespace(_collection=collection)
    manager._get_store = lambda _kb_id: store
    manager._get_existing_ids = lambda _store, _ids: set()

    chunks = [
        SimpleNamespace(
            id=index + 1,
            doc_id=10,
            text=str(index),
            _extra_metadata={},
        )
        for index in range(4)
    ]

    manager.add_chunks(kb_id=1, chunks=chunks, embed_batch_size=4)

    assert len(collection.add_calls) == 1
    assert collection.add_calls[0]["ids"] == ["1", "2", "3", "4"]
    assert collection.add_calls[0]["embeddings"] == [
        [0.0],
        [1.0],
        [2.0],
        [3.0],
    ]


def test_add_chunks_rejects_oversized_chunk_before_embedding():
    manager = object.__new__(VectorStoreManager)
    manager.embedding = _SizeLimitedEmbedding(maximum_batch_size=64)
    manager.embedding_input_guard = _lightweight_guard(10)
    collection = _CollectionSpy()
    store = SimpleNamespace(_collection=collection)
    manager._get_store = lambda _kb_id: store
    manager._get_existing_ids = lambda _store, _ids: set()
    chunk = SimpleNamespace(
        id=1,
        doc_id=10,
        text="测" * 20,
        _extra_metadata={},
    )

    with pytest.raises(EmbeddingInputTooLongError, match="split it before"):
        manager.add_chunks(kb_id=1, chunks=[chunk], embed_batch_size=64)

    assert manager.embedding.calls == []
    assert collection.add_calls == []


def test_similarity_search_truncates_query_before_embedding():
    manager = object.__new__(VectorStoreManager)
    manager.embedding = _QueryEmbedding()
    manager.embedding_input_guard = _lightweight_guard(10)
    store = SimpleNamespace(_collection=_CollectionSpy())
    manager._get_store = lambda _kb_id: store

    assert manager.similarity_search(kb_id=1, query="测" * 30) == []

    assert len(manager.embedding.queries) == 1
    assert manager.embedding_input_guard.fits(manager.embedding.queries[0])


def test_vector_registry_passes_embedding_input_limit(monkeypatch):
    captured: dict = {}

    class _KnowledgeBaseDatabase:
        async def get_kb(self, _kb_id):
            return SimpleNamespace(embedding_id=9)

    class _EmbeddingDatabase:
        async def get_by_id(self, _embedding_id):
            return SimpleNamespace(
                base_url="http://localhost:11434",
                model_name="embedding-model",
                max_input_tokens=768,
            )

    def _vector_store_factory(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr(
        "app.runtime.vector_registry.VectorStoreManager",
        _vector_store_factory,
    )
    registry = object.__new__(VectorStoreRegistry)
    registry.kb_db = _KnowledgeBaseDatabase()
    registry.embed_db = _EmbeddingDatabase()

    asyncio.run(registry._build_store(1))

    assert captured["max_input_tokens"] == 768


def test_smart_router_truncates_query_and_kb_description(monkeypatch):
    embedding_instances: list[_QueryEmbedding] = []

    class _EmbeddingDatabase:
        async def get_by_name(self, _name):
            return SimpleNamespace(
                base_url="http://localhost:11434",
                model_name="embedding-model",
                max_input_tokens=10,
            )

    class _KnowledgeBaseServices:
        async def get_kb_info(self, kb_id):
            return SimpleNamespace(
                name=f"kb-{kb_id}",
                description="测" * 30,
                keywords=[],
            )

    def _embedding_factory(**_kwargs):
        embedding = _QueryEmbedding()
        embedding_instances.append(embedding)
        return embedding

    monkeypatch.setattr(
        "app.services.kb.smart_router.OllamaEmbeddings",
        _embedding_factory,
    )
    router = object.__new__(SmartRouter)
    router.embedding_db = _EmbeddingDatabase()
    router.kb_services = _KnowledgeBaseServices()
    router.router_config = SimpleNamespace(
        extra_config={"embedding_provider_name": "configured-embedding"},
        max_kb_count=1,
    )

    async def _get_kb_embedding(kb_id, embedding, input_guard):
        return await router._build_kb_embedding(
            kb_id,
            embedding,
            input_guard,
        )

    router._get_kb_embedding = _get_kb_embedding
    selected = asyncio.run(router._select_kbs_by_embedding("测" * 30, [1]))

    assert selected == [1]
    assert len(embedding_instances) == 1
    assert len(embedding_instances[0].queries) == 2
    guard = _lightweight_guard(9)
    assert all(guard.fits(text) for text in embedding_instances[0].queries)

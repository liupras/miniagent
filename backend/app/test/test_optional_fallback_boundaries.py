#!/usr/bin/python
# -*- coding:utf-8 -*-

import threading
from types import SimpleNamespace

import pytest
from chromadb.errors import NotFoundError as ChromaNotFoundError

import app.retrieval.vector_store as vector_store_module
from app.infra.search.bm25_manager import BM25Manager
from app.retrieval.reranker.base import RerankMode
from app.retrieval.reranker.bge import BGEReranker
from app.retrieval.reranker.exceptions import RerankerLoadError
from app.retrieval.reranker.factory import RerankerFactory
from app.retrieval.vector_store import VectorStoreManager


@pytest.mark.parametrize("error", [OSError("missing"), UnicodeError("bad encoding")])
def test_stopword_loading_only_degrades_for_known_file_errors(monkeypatch, error):
    manager = object.__new__(BM25Manager)
    manager._get_topwords_file_path = lambda: "stopwords.txt"

    def broken_open(*args, **kwargs):
        raise error

    monkeypatch.setattr("builtins.open", broken_open)

    assert manager._load_stopwords() == set()


def test_stopword_loading_does_not_swallow_program_errors(monkeypatch):
    manager = object.__new__(BM25Manager)
    manager._get_topwords_file_path = lambda: "stopwords.txt"

    def broken_open(*args, **kwargs):
        raise RuntimeError("program error")

    monkeypatch.setattr("builtins.open", broken_open)

    with pytest.raises(RuntimeError, match="program error"):
        manager._load_stopwords()


def test_known_reranker_load_error_falls_back_to_hybrid(monkeypatch):
    def fail_to_load(**kwargs):
        raise RerankerLoadError("model unavailable")

    monkeypatch.setattr(BGEReranker, "local", fail_to_load)

    reranker = RerankerFactory.create(
        mode=RerankMode.BGE,
        reranker_config={"backend": "local"},
    )

    assert reranker._mode == RerankMode.SCORE
    assert reranker._reranker is None


def test_reranker_creation_does_not_swallow_program_errors(monkeypatch):
    def broken_factory(**kwargs):
        raise TypeError("program error")

    monkeypatch.setattr(BGEReranker, "local", broken_factory)

    with pytest.raises(TypeError, match="program error"):
        RerankerFactory.create(
            mode=RerankMode.BGE,
            reranker_config={"backend": "local"},
        )


class _ChromaClient:
    def __init__(self, *, get_error=None, delete_error=None) -> None:
        self.get_error = get_error
        self.delete_error = delete_error

    def get_collection(self, name):
        if self.get_error is not None:
            raise self.get_error
        return SimpleNamespace(metadata={})

    def delete_collection(self, name):
        if self.delete_error is not None:
            raise self.delete_error


def _store_manager(client) -> VectorStoreManager:
    manager = object.__new__(VectorStoreManager)
    manager._chroma_client = client
    manager._stores = {}
    manager._lock = threading.Lock()
    manager.vector_dim = 3
    manager.embedding = SimpleNamespace(model="embedding-model")
    return manager


def test_missing_chroma_collection_uses_creation_compatibility_path(monkeypatch):
    manager = _store_manager(
        _ChromaClient(get_error=ChromaNotFoundError("missing"))
    )
    created_store = SimpleNamespace()
    monkeypatch.setattr(
        vector_store_module,
        "Chroma",
        lambda **kwargs: created_store,
    )

    assert manager._get_store(1) is created_store


def test_collection_lookup_does_not_treat_program_error_as_missing(monkeypatch):
    manager = _store_manager(_ChromaClient(get_error=RuntimeError("program error")))
    monkeypatch.setattr(
        vector_store_module,
        "Chroma",
        lambda **kwargs: pytest.fail("must not create a replacement collection"),
    )

    with pytest.raises(RuntimeError, match="program error"):
        manager._get_store(1)


def test_drop_collection_only_ignores_already_absent_collection():
    manager = _store_manager(
        _ChromaClient(delete_error=ChromaNotFoundError("missing"))
    )
    manager._stores[1] = SimpleNamespace()

    manager.drop_collection(1)

    assert 1 not in manager._stores


def test_drop_collection_propagates_unknown_failure_and_keeps_cached_store():
    manager = _store_manager(
        _ChromaClient(delete_error=RuntimeError("program error"))
    )
    cached_store = SimpleNamespace()
    manager._stores[1] = cached_store

    with pytest.raises(RuntimeError, match="program error"):
        manager.drop_collection(1)

    assert manager._stores[1] is cached_store


def _search_manager(query_function) -> VectorStoreManager:
    manager = object.__new__(VectorStoreManager)
    manager.embedding_input_guard = SimpleNamespace(truncate_text=lambda text: text)
    manager.embedding = SimpleNamespace(embed_query=lambda text: [1.0])
    collection = SimpleNamespace(query=query_function)
    manager._get_store = lambda kb_id: SimpleNamespace(_collection=collection)
    return manager


def test_invalid_where_clause_retries_without_filter():
    calls = []

    def query(**kwargs):
        calls.append(kwargs)
        if "where" in kwargs:
            raise ValueError("unsupported filter")
        return {"ids": [[]], "metadatas": [[]], "distances": [[]]}

    manager = _search_manager(query)

    assert manager.similarity_search(
        kb_id=1,
        query="query",
        metadata_filter={"doc_id": 1},
    ) == []
    assert len(calls) == 2
    assert "where" not in calls[1]


def test_vector_search_does_not_convert_program_error_to_empty_result():
    manager = _search_manager(
        lambda **kwargs: (_ for _ in ()).throw(TypeError("program error"))
    )

    with pytest.raises(TypeError, match="program error"):
        manager.similarity_search(
            kb_id=1,
            query="query",
            metadata_filter={"doc_id": 1},
        )

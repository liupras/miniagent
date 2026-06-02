#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-19
# @description: The BM25 index manager. It has been adapted to the LangChain BaseStore interface, supporting a smooth migration to Redis in the future.

import os
import json
import time
import pickle
import jieba
import numpy as np
from typing import List, Dict, Optional

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from pydantic import Field, ConfigDict

from loguru import logger
from rank_bm25 import BM25Okapi
from langchain_core.stores import BaseStore
from app.infra.cache_backend import create_cache_backend

class BM25Manager:

    def __init__(
        self,
        storage_dir: str = "./bm25_storage",
        cache_backend: Optional[BaseStore] = None,
        backend_type: str = "memory",
        max_cache_size: int = 1000,
        small_corpus_threshold: int = 3
    ):
        self.storage_dir = storage_dir      

        self.cache = cache_backend or create_cache_backend(
            backend_type,
            max_size=max_cache_size
        )

        self.stopwords = self._load_stopwords()
        self.small_corpus_threshold = small_corpus_threshold

    # ==========================================
    # Basic tools
    # ==========================================

    def _docs_key(self, kb_id: str):
        return f"bm25:docs:{kb_id}"

    def _obj_key(self, kb_id: str):
        return f"bm25:obj:{kb_id}"

    def _storage_path(self, kb_id: str):
        return os.path.join(self.storage_dir, f"{kb_id}.json")
    
    def _get_topwords_file_path(self):
        import pathlib
        # 1. Get the path object of the currently executing file
        current_file = pathlib.Path(__file__)
        # 2. Get the folder where the current file is located (Core: get the folder first, then construct the file name).
        current_dir = current_file.parent
        # 3. Concatenate filenames (using the / operator)
        file_path = current_dir / "stopwords.txt"
        return file_path

    def _load_stopwords(self):
        stopwords = set()        
        try:
            with open(self._get_topwords_file_path(), "r", encoding="utf-8") as f:
                for line in f:
                    word = line.strip()
                    if word and not word.startswith("#"):
                        stopwords.add(word)
        except Exception as e:
            logger.error(f"❌ Load stopwords failed: {e}")
        return stopwords

    def tokenize(self, text: str):
        tokens = jieba.cut(text)
        return [t for t in tokens if t not in self.stopwords and t.strip()]

    # ==========================================
    # persistence
    # ==========================================

    def _load_from_disk(self, kb_id: str) -> List[Dict]:
        path = self._storage_path(kb_id)
        if not os.path.exists(path):
            return []

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("docs", [])

    def _save_to_disk(self, kb_id: str, docs: List[Dict]):
        path = self._storage_path(kb_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "docs": docs,
                "updated_at": int(time.time())
            }, f, ensure_ascii=False)

    # ==========================================
    # BM25 Build/Load
    # ==========================================

    def _get_docs(self, kb_id: str) -> List[Dict]:
        """Retrieve a list of documents from BaseStore; if missing, load them from disk."""
        keys = [self._docs_key(kb_id)]
        results = self.cache.mget(keys)
        docs_bytes = results[0]
        if docs_bytes:
            return pickle.loads(docs_bytes)

        # cache miss → load from disk
        docs = self._load_from_disk(kb_id)
        self.cache.mset([(self._docs_key(kb_id), pickle.dumps(docs))])
        return docs

    def _build_bm25(self, kb_id: str):
        docs = self._get_docs(kb_id)
        if not docs:
            return None, []

        corpus = [doc["tokens"] for doc in docs]
        bm25 = BM25Okapi(corpus)

        # Cache bm25 objects (cached only to CacheBackend)
        self.cache.mset([(self._obj_key(kb_id), pickle.dumps(bm25))])

        return bm25, docs

    def _get_bm25(self, kb_id: str):
        keys = [self._obj_key(kb_id), self._docs_key(kb_id)]
        results = self.cache.mget(keys)
        
        obj_bytes, docs_bytes = results[0], results[1]

        if obj_bytes and docs_bytes:
            return pickle.loads(obj_bytes), pickle.loads(docs_bytes)

        return self._build_bm25(kb_id)

    # ==========================================
    # Document Management
    # ==========================================

    def add_documents(self, kb_id: str, documents: List[Dict]):
        """
        documents = [
            {"chunk_id": "...", "text": "..."}
        ]
        """

        docs = self._get_docs(kb_id)
        doc_map = {doc["id"]: doc for doc in docs}

        for doc in documents:
            tokens = self.tokenize(doc["text"])
            doc_map[doc["chunk_id"]] = {
                "id": doc["chunk_id"],
                "tokens": tokens,
                "metadata":doc["_extra_metadata"],
                "text": doc["text"]
            }

        updated_docs = list(doc_map.values())

        self._save_to_disk(kb_id, updated_docs)
 
        # Update cache: Set up the new document while deleting the old BM25 index object (forcing it to be rebuilt on the next search).
        self.cache.mset([(self._docs_key(kb_id), pickle.dumps(updated_docs))])
        self.cache.mdelete([self._obj_key(kb_id)])

    def delete_documents(self, kb_id: str, chunk_ids: List[str]):
        docs = self._get_docs(kb_id)
        filtered = [doc for doc in docs if doc["id"] not in chunk_ids]

        self._save_to_disk(kb_id, filtered)
        self.cache.mset([(self._docs_key(kb_id), pickle.dumps(filtered))])
        self.cache.mdelete([self._obj_key(kb_id)])

    # ==========================================
    # search(Includes logic for handling negative scores)
    # ==========================================

    def search(self, kb_id: str, query: str, top_k: int = 30,
               score_threshold:float=0.1):
        tokenized_query = self.tokenize(query)
        if not tokenized_query:
            return []        

        docs = self._get_docs(kb_id)

        if not docs:
            return []

        #  Small corpora can directly use simple TF logic to avoid the negative score problem of BM25 with small samples.
        if len(docs) <= self.small_corpus_threshold:
            return self._tf_search(docs, tokenized_query, top_k)

        # BM25
        bm25, docs = self._get_bm25(kb_id)
        if not bm25:
            return []

        scores = bm25.get_scores(tokenized_query)
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            # Filter out possible negative or zero scores
            if scores[idx] <= score_threshold:
                continue

            results.append({
                "id": docs[idx]["id"],
                "score": float(scores[idx]),
                "metadata":docs[idx]["metadata"],
                "text": docs[idx]["text"]
            })

        return results
    
    def _tf_search(self, docs, tokenized_query, top_k):
        """
        Simple frequency search logic

        When a keyword is so common that it appears in more than half of the documents, the rank_bm25 score may be negative.
        In this case, use this function to calculate the score.
        """
        results = []

        for doc in docs:
            score = 0
            token_counts = {}

            for t in doc["tokens"]:
                token_counts[t] = token_counts.get(t, 0) + 1

            for q in tokenized_query:
                score += token_counts.get(q, 0) / len(doc["tokens"])

            if score > 0:
                results.append({
                    "id": doc["id"],
                    "score": float(score),
                    "text": doc["text"]
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    # ==========================================
    # Management Interface
    # ==========================================

    def clear_cache(self, kb_id: Optional[str] = None):
        """Clear the cache. Since the BaseStore interface does not uniformly support `clear`, delete manually by key."""
        if kb_id:
            self.cache.mdelete([self._obj_key(kb_id), self._docs_key(kb_id)])
        else:
            # If it's a MemoryCacheStore, we previously defined a custom clear method.
            if hasattr(self.cache, 'clear'):
                self.cache.clear()
            else:
                logger.warning("Currently, CacheBackend does not support global cleanup.")

    def as_retriever(
        self,
        kb_id: str,
        top_k:   int   = 30,
        score_threshold: float   = 0.1
    ) -> "BM25Retriever":
        """
        Factory method — returns a LangChain BaseRetriever bound to this manager.

        Args:
            kb_id: Target knowledge base name (matches the key used in add_documents).
            top_k:   Maximum number of results to return.

        Returns:
            BM25Retriever — drop-in BaseRetriever for any LangChain chain.
        """
        return BM25Retriever(
            bm25_manager = self,
            kb_id      = kb_id,
            top_k        = top_k,
            score_threshold = score_threshold
        )
    
# ==========================================================
# LangChain Retriever Adapter
# ==========================================================

class BM25Retriever(BaseRetriever):
    """
    LangChain-compatible retriever backed by BM25Manager.

    Wraps a BM25Manager instance so it can be plugged directly into
    any LangChain pipeline that accepts a BaseRetriever
    (RetrievalQA, ConversationalRetrievalChain, LCEL | operator, etc.).

    Example
    -------
    ::

        bm25 = BM25Manager(storage_dir="./bm25_storage")
        retriever = bm25.as_retriever(kb_id="my_kb", top_k=20)

        # LCEL
        chain = retriever | some_llm

        # RetrievalQA
        qa = RetrievalQA.from_chain_type(llm=llm, retriever=retriever)
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    bm25_manager: BM25Manager = Field(..., exclude=True)
    kb_id:      str
    top_k:        int         = 30
    score_threshold: float    = 0.1

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> List[Document]:
        """
        Called by LangChain internals for every retrieval request.
        Converts BM25 search results into standard LangChain Document objects.

        Each Document carries:
            page_content      — the chunk text
            metadata.chunk_id — original chunk id stored in BM25 index
            metadata.retrieval_score  — BM25 / TF score
            metadata.retrieval_type   — "bm25"
        """
        results = self.bm25_manager.search(
            kb_id = self.kb_id,
            query   = query,
            top_k   = self.top_k,
            score_threshold = self.score_threshold
        )
        docs = []
        for item in results:
            docs.append(Document(
                page_content = item["text"],
                metadata     = {
                    "chunk_id":       item["id"],
                    "retrieval_score": round(item["score"], 4),
                    "retrieval_type":  "bm25",
                },
            ))
        return docs


    # ==========================================
    # Test cases
    # ==========================================
def test_add_and_search(temp_manager):
    kb = "test_kb"

    docs = [
        {"chunk_id": "1", "text": "中国的首都是北京"},
        {"chunk_id": "2", "text": "北京是一个国际化大都市"},
        {"chunk_id": "3", "text": "上海是中国的经济中心"},
    ]

    temp_manager.add_documents(kb, docs)

    results = temp_manager.search(kb, "北京", top_k=3)

    assert len(results) >= 2
    assert results[0]["id"] in ["1", "2"]

def test_delete_documents(temp_manager):
    kb = "delete_kb"

    docs = [
        {"chunk_id": "1", "text": "苹果很好吃"},
        {"chunk_id": "2", "text": "香蕉很好吃"},
    ]

    temp_manager.add_documents(kb, docs)

    temp_manager.delete_documents(kb, ["1"])

    results = temp_manager.search(kb, "苹果", top_k=5)

    assert len(results) == 0

def test_overwrite_document(temp_manager):
    kb = "overwrite_kb"

    temp_manager.add_documents(kb, [
        {"chunk_id": "1", "text": "旧内容"}
    ])

    temp_manager.add_documents(kb, [
        {"chunk_id": "1", "text": "新内容"}
    ])

    results = temp_manager.search(kb, "新内容", top_k=5)

    assert len(results) == 1
    assert results[0]["text"] == "新内容"

def test_persistence_across_restart():
    import tempfile, shutil
    temp_dir = tempfile.mkdtemp()

    cache = MemoryCacheStore(max_size=100)
    manager = BM25Manager(
        storage_dir=temp_dir,
        cache_backend=cache
    )

    kb = "persist_kb"

    manager.add_documents(kb, [
        {"chunk_id": "1", "text": "持久化测试文档"}
    ])

    # Simulate a restart (re-instantiate)
    new_manager = BM25Manager(
        storage_dir=temp_dir,
        cache_backend=MemoryCacheStore(max_size=100)
    )

    results = new_manager.search(kb, "持久化", top_k=5)

    shutil.rmtree(temp_dir)

    assert len(results) == 1
    assert results[0]["id"] == "1"

def test_multiple_kb_isolation(temp_manager):
    temp_manager.add_documents("kb1", [
        {"chunk_id": "1", "text": "北京"}
    ])

    temp_manager.add_documents("kb2", [
        {"chunk_id": "2", "text": "上海"}
    ])

    r1 = temp_manager.search("kb1", "北京", top_k=5)
    r2 = temp_manager.search("kb2", "上海", top_k=5)

    assert len(r1) == 1
    assert len(r2) == 1

def test_large_dataset(temp_manager):
    kb = "large_kb"

    docs = []
    for i in range(500):
        docs.append({
            "chunk_id": str(i),
            "text": f"这是第{i}个测试文档"
        })

    temp_manager.add_documents(kb, docs)

    results = temp_manager.search(kb, "文档", top_k=10)

    assert len(results) == 10

def test_empty_kb(temp_manager):
    results = temp_manager.search("empty_kb", "文档", top_k=5)
    assert results == []

def test_cache_hit(temp_manager):
    kb = "cache_kb"

    temp_manager.add_documents(kb, [
        {"chunk_id": "1", "text": "缓存测试文档"}
    ])

    # The first search will build bm25
    temp_manager.search(kb, "缓存", top_k=5)

    stats_before = temp_manager.cache.get_stats()["hits"]

    # The second search should hit the cache.
    temp_manager.search(kb, "缓存", top_k=5)

    stats_after = temp_manager.cache.get_stats()["hits"]

    assert stats_after > stats_before

if __name__ == "__main__":

    import os,sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from app.core.config import settings
    from app.infra.cache_backend import MemoryCacheStore
    cache = create_cache_backend(
        "memory",
        max_size=settings.bm25_max_cache_size
    )
    manager = BM25Manager(    
        storage_dir=settings.bm25_index_path,    
        cache_backend=cache
    )
    
    test_add_and_search(manager)
    test_delete_documents(manager)
    test_overwrite_document(manager)    
    test_persistence_across_restart()
    test_multiple_kb_isolation(manager)
    test_empty_kb(manager)
    test_large_dataset(manager)
    test_cache_hit(manager)
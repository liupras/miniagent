#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-27
# @description: Vector store layer — wraps langchain_chroma.Chroma (chromadb local).
#   Key design notes
#   ─────────────────
#   • One Chroma collection per knowledge base, named "kb_{kb_id}".
#   • We manage *one* Chroma instance per collection via a local cache so
#     connections are reused rather than reopened on every call.
#   • `chunk_db_id` (the SQLite Chunk.id) is used as the Chroma document ID (str).
#   • `doc_id` is stored as metadata so we can delete all chunks of a document at once.
"""
Optimized for:
    - 500k chunks
    - CPU environment
    - Windows native
    - Deterministic primary key
"""

from typing import Dict, List, Optional, Tuple,Any
from pydantic import Field, ConfigDict

from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from loguru import logger
import threading
import chromadb
from chromadb.config import Settings
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from tqdm import tqdm

# ==========================================================
# CONSTANTS
# ==========================================================

# Chroma uses cosine similarity natively; no explicit index config needed.
# Results from similarity_search_with_relevance_scores are in [0, 1], higher = more similar.
IN_QUERY_BATCH_SIZE = 1000   # Max IDs per single get() call
ADD_BATCH_SIZE      = 5000   # Chroma recommends batching large inserts

# ==========================================================
# VectorStoreManager
# ==========================================================
class VectorStoreManager:
    """
    Manages per-KB Chroma collections via langchain_chroma.

    Embedding model: quentinz/bge-large-zh-v1.5 (served by Ollama).
    Override at construction time to swap the model:

        from langchain_openai import OpenAIEmbeddings
        vsm = VectorStoreManager(embeddings=OpenAIEmbeddings(...))

    Usage:
        vsm = VectorStoreManager()
        vsm.add_chunks(kb_id=1, chunks=small_chunks)
        vsm.delete_by_doc_id(kb_id=1, doc_id=42)
        results = vsm.similarity_search(kb_id=1, query="...", top_k=10)
    """

    # Metadata field names
    PRIMARY_FIELD = "chunk_db_id"   # int  — SQLite Chunk.id (also used as Chroma doc ID)
    DOC_ID_FIELD  = "doc_id"        # int  — SQLite Document.id
    TEXT_FIELD    = "text"          # str  — Raw text (Chroma stores this as document content)

    def __init__(
        self,
        db_path:        str = "./data/vector",        
        ollama_base_url: str = "http://localhost:11434",
        embed_model: str = "quentinz/bge-large-zh-v1.5",        
        vector_dim:int=1024   # kept for API compatibility, Chroma auto-detects  
    ):
        """
        Args:
            db_path:          Local directory path for ChromaDB persistent storage.
            ollama_base_url: Base URL for the Ollama embeddings service.
            embed_model:     Embedding model name served by Ollama.
            vector_dim:      Embedding dimension (informational; Chroma auto-detects).                    
        """
        self.vector_dim = vector_dim
        self.embedding  = OllamaEmbeddings(
            model=embed_model,
            base_url=ollama_base_url,
        )
        # Persistent ChromaDB client shared across all collections
        self._chroma_client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._stores: Dict[int, Chroma] = {}  # kb_id → Chroma instance
        self._lock = threading.Lock()  # To synchronize access to _clients

    # ==========================================================
    # Internal
    # ==========================================================
    def _get_collection_name(self, kb_id: int) -> str:
        return f"kb_{kb_id}"
    
    def _chunk_id_to_str(self, chunk_id: int) -> str:
        """Chroma requires string IDs."""
        return str(chunk_id)
    
    def _get_existing_ids(self, store: Chroma, chunk_ids: List[int]) -> set:
        """Return the subset of chunk_ids that already exist in the collection."""
        if not chunk_ids:
            return set()

        existing = set()
        str_ids = [self._chunk_id_to_str(cid) for cid in chunk_ids]

        for start in range(0, len(str_ids), IN_QUERY_BATCH_SIZE):
            batch = str_ids[start:start + IN_QUERY_BATCH_SIZE]
            result = store.get(ids=batch, include=[])   # include=[] → only IDs returned
            for sid in result["ids"]:
                existing.add(int(sid))

        return existing
    
    def _detect_embedding_dim(self) -> int:
        """
        Detect embedding dimension once and cache it.
        """
        if self.vector_dim is not None:
            return self.vector_dim

        test_vec = self.embedding.embed_query("dimension test")
        self.vector_dim = len(test_vec)
        return self.vector_dim

    def _get_store(self, kb_id: int,
                   collection_name: Optional[str] = None,) -> Chroma:
        """
        Return (and lazily create) the Chroma vectorstore for kb_id.
        Thread-safe via _lock.
        """
        with self._lock:
            if kb_id in self._stores:
                return self._stores[kb_id]
            
            col_name = collection_name or self._get_collection_name(kb_id)
            expected_dim = self._detect_embedding_dim()

            """
            Detection embedding model and dimension
            """
            try:
                collection = self._chroma_client.get_collection(col_name)
                exists = True
            except Exception:
                exists = False
                collection = None

            if not exists:
                store = Chroma(
                    client=self._chroma_client,
                    collection_name=col_name,
                    embedding_function=self.embedding,
                    collection_metadata={
                        "hnsw:space": "cosine",
                        "embed_model": self.embedding.model,
                        "embedding_dim": expected_dim,
                    },
                )
                logger.info(f"[Chroma] Created new collection: {col_name}")
            else:
                # Exists → Validate metadata
                metadata = collection.metadata or {}

                stored_model = metadata.get("embed_model")
                stored_dim   = metadata.get("embedding_dim")

                if stored_model and stored_model != self.embedding.model:
                    raise RuntimeError(
                        f"""Embedding model mismatch for collection {col_name}

                        Stored model:   {stored_model}
                        Current model:  {self.embedding.model}

                        You must rebuild this KB index.
                        """
                    )

                if stored_dim and stored_dim != expected_dim:
                    raise RuntimeError(
                        f"""Embedding dimension mismatch for collection {col_name}

                        Stored dimension:   {stored_dim}
                        Current dimension:  {expected_dim}

                        You must rebuild this KB index.
                        """
                    )

                store = Chroma(
                    client=self._chroma_client,
                    collection_name=col_name,
                    embedding_function=self.embedding,
                )

            logger.info(f"[Chroma] Opened collection: {col_name}")
            self._stores[kb_id] = store
            return store

    def drop_collection(self, kb_id: int) -> None:
        """Drop the entire collection for a KB (e.g. on KB deletion)."""
        with self._lock:
            collection_name = self._get_collection_name(kb_id)
            try:
                self._chroma_client.delete_collection(collection_name)
                logger.info(f"[Chroma] Dropped collection: {collection_name}")
            except Exception as e:
                logger.warning(f"[Chroma] drop_collection({collection_name}) failed: {e}")
            finally:
                self._stores.pop(kb_id, None)

    # =========================================================================
    # Write
    # =========================================================================
    def add_chunks(
        self,
        kb_id: int,
        chunks,                     # List[database.Chunk] — must have .id set
        embed_batch_size: int = 64,
        on_batch: Optional[callable] = None,
    ) -> None:
        """
        Embed and insert chunks in batches.
        Supports resume download and skips existing chunk_db_id.

        Args:
            kb_id       : knowledge base id
            chunks      : SQLAlchemy Chunk objects (must have .id already populated)
            embed_batch_size  : texts per embedding call
            on_batch    : optional callback(done, total) called after each batch
        """
        if not chunks:
            return
        
        store = self._get_store(kb_id)
        
        # De-duplicate: skip chunks that are already stored
        chunk_ids = [c.id for c in chunks]
        existing_ids = self._get_existing_ids(store, chunk_ids)
        new_chunks = [c for c in chunks if c.id not in existing_ids]

        if not new_chunks:
            logger.info("[Chroma] All chunks already exist.")
            return 

        total = len(new_chunks)
        logger.info(f"[Chroma] KB {kb_id} is preparing to embed {len(new_chunks)} new blocks.")

        pbar = tqdm(total=total, desc=f"KB {kb_id} Embedding", unit="chunk")

        # Execute Embedding (CPU-intensive operation) in batches
        for start in range(0, total, embed_batch_size):
            batch = new_chunks[start: start + embed_batch_size]

            # Embed batch
            texts = [c.text for c in batch]
            vectors = self.embedding.embed_documents(texts)

            ids       = []
            documents = []
            metadatas = []
            embeddings_list = []

            for i, c in enumerate(batch):
                ids.append(self._chunk_id_to_str(c.id))
                documents.append(c.text)
                embeddings_list.append(vectors[i])
                meta = {
                    self.PRIMARY_FIELD: c.id,
                    self.DOC_ID_FIELD:  c.doc_id,
                }
                # Inherit any extra metadata from the Chunk object
                extra_meta = getattr(c, '_extra_metadata', {})
                # Chroma metadata values must be str / int / float / bool
                for k, v in extra_meta.items():
                    if isinstance(v, (str, int, float, bool)):
                        meta[k] = v
                metadatas.append(meta)                

            # Add pre-computed embeddings directly to avoid double-embedding
            # The raw text is stored in sqlite
            store._collection.add(
                ids=ids,
                embeddings=embeddings_list,
                metadatas=metadatas,
            )           

            done = min(start + embed_batch_size, total)
            logger.debug(f"[Chroma] kb={kb_id} Embedding progress: {done}/{total}")

            pbar.update(len(batch))

            if on_batch:
                on_batch(done, total) 

        pbar.close()      

    # ==========================================================
    # Delete
    # ==========================================================
    def delete_by_doc_id(self, kb_id: int, doc_id: int) -> None:
        """Remove all vectors that belong to doc_id."""
        store = self._get_store(kb_id)
        store.delete(where={self.DOC_ID_FIELD: doc_id})
        logger.debug(f"[Chroma] Deleted vectors for doc_id={doc_id} in kb={kb_id}")

    def delete_by_chunk_ids(self, kb_id: int, chunk_ids: List[int]) -> None:
        """Remove specific vectors by their SQLite Chunk.id."""
        if not chunk_ids:
            return
        store = self._get_store(kb_id)
        str_ids = [self._chunk_id_to_str(cid) for cid in chunk_ids]
        for start in range(0, len(str_ids), IN_QUERY_BATCH_SIZE):
            batch = str_ids[start:start + IN_QUERY_BATCH_SIZE]
            store.delete(ids=batch)

        logger.debug(f"[Chroma] Deleted {len(chunk_ids)} vectors in kb={kb_id}")

    # =========================================================================
    # Search
    # =========================================================================
    @staticmethod
    def _build_where(metadata_filter: Optional[dict]) -> Optional[dict]:
        """
        Convert metadata_filter into a valid Chroma where clause.
        Returns None if the filter is empty or cannot be made valid.
        """
        if not metadata_filter:
            return None

        # ── Top-level logical operators ($and / $or / $nor): recursive validation clauses ───
        if any(k.startswith("$") for k in metadata_filter):
            validated = VectorStoreManager._validate_logical_clause(metadata_filter)
            return validated  # None indicates that the validation failed and will be downgraded to no filtering.

        # ── Regular field filtering: Field-by-field cleaning ───────────
        clauses = []
        for field, value in metadata_filter.items():
            clause = VectorStoreManager._build_field_clause(field, value)
            if clause is not None:
                clauses.append(clause)

        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}


    @staticmethod
    def _build_field_clause(field: str, value: Any) -> Optional[dict]:
        """
        Converts a single field into a Chroma WHERE clause, returning None if invalid.

        Support：
            {"doc_id": 42}              → {"doc_id": {"$eq": 42}}
            {"doc_id": {"$in": [1,2]}}  → {"doc_id": {"$in": [1,2]}}
            {"doc_id": {"$in": []}}     → None  
            {"doc_type": None}          → None 
            {"doc_type": ["law"]}       → None  
        """
        VALID_SCALAR_TYPES = (str, int, float, bool)
        VALID_OPERATORS = {"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin"}

        # The value is dict, indicating that it is already an operator expression.
        if isinstance(value, dict):
            if not value:
                return None
            op, op_val = next(iter(value.items()))
            if op not in VALID_OPERATORS:
                logger.warning(f"[Chroma] Unknown operator '{op}' for field '{field}' — skipped.")
                return None
            # $in / $nin must be a non-empty list
            if op in ("$in", "$nin"):
                if not isinstance(op_val, list) or len(op_val) == 0:
                    logger.warning(
                        f"[Chroma] '{op}' for field '{field}' has empty or invalid list — skipped."
                    )
                    return None
            return {field: value}

        # Value is a scalar
        if isinstance(value, VALID_SCALAR_TYPES):
            return {field: {"$eq": value}}

        # Other types (None, list, dict, etc.): Discard
        logger.warning(
            f"[Chroma] Field '{field}' has unsupported value type "
            f"{type(value).__name__} — skipped."
        )
        return None

    @staticmethod
    def _validate_logical_clause(clause: dict) -> Optional[dict]:
        """
        Validate top-level logical clauses such as $and and $or to ensure that the number of clauses is >= 2.
        Return None if there are insufficient clauses (degradation to no filtering).
        """
        result = {}
        for op, sub_clauses in clause.items():
            if op in ("$and", "$or", "$nor"):
                if not isinstance(sub_clauses, list):
                    logger.warning(f"[Chroma] '{op}' value must be a list — skipped.")
                    return None
                # Recursively check each clause
                valid_subs = []
                for sub in sub_clauses:
                    validated_sub = VectorStoreManager._build_where(sub)
                    if validated_sub is not None:
                        valid_subs.append(validated_sub)
                # Chroma requires at least two clauses for $and/$or.
                if len(valid_subs) == 0:
                    return None
                if len(valid_subs) == 1:
                    # With only one left, return directly to that clause, removing the outer logical operator.
                    logger.debug(f"[Chroma] '{op}' reduced to single clause, unwrapping.")
                    return valid_subs[0]
                result[op] = valid_subs
            else:
                # Other operators starting with $ are passed through directly.
                result[op] = sub_clauses
        return result or None
    
    def similarity_search(
        self,
        kb_id: int,
        query: str,
        top_k: int = 10,
        score_threshold: float = 0.5,   # BGE cosine: >0.7 is highly relevant
        metadata_filter:  Optional[dict] = None,
    ) -> List[Tuple[Document, float]]:
        """
        Return (Document, score) pairs sorted by relevance (highest first).
        Score is cosine similarity in [0, 1].
        Returns [] if the collection is empty or search fails.

        metadata_filter examples
        ------------------------
        # Single field equality
        metadata_filter={"doc_id": 42}

        # Multiple fields (auto-combined with $and)
        metadata_filter={"doc_id": 42, "section": "intro"}

        # Operator expressions
        metadata_filter={"doc_id": {"$in": [1, 2, 3]}}
        metadata_filter={"score": {"$gte": 0.8}}

        # Complex logic — pass raw Chroma where dict directly
        metadata_filter={"$or": [{"doc_id": 1}, {"doc_id": 2}]}
        metadata_filter={"$and": [{"$or": [{"doc_id": 1}, {"doc_id": 2}]},
                                   {"section": {"$eq": "intro"}}]}

        Supported operators: $eq $ne $gt $gte $lt $lte $in $nin
        """            
        try:
            store = self._get_store(kb_id)
            where = self._build_where(metadata_filter)
            logger.debug(f"[Chroma] similarity_search kb={kb_id} where={where}")

            query_vector = self.embedding.embed_query(query)

            query_kwargs: dict = {
                "query_embeddings": [query_vector],
                "n_results": top_k,
                "include": ["metadatas", "distances", "embeddings"],
                # Note: Do not include "documents" because we are storing an empty placeholder string.
            }
            if where is not None:
                query_kwargs["where"] = where

            try:
                raw = store._collection.query(**query_kwargs)
            except Exception as where_exc:
                if where is not None:
                    # If the WHERE condition causes an exception, it will be downgraded to a full query without the WHERE clause.
                    logger.warning(
                        f"[Chroma] where clause {where} caused error: {where_exc}. "
                        f"Retrying without filter."
                    )
                    query_kwargs.pop("where")
                    raw = store._collection.query(**query_kwargs)
                else:
                    raise

            # raw structure: {"ids": [[...]], "metadatas": [[...]], "distances": [[...]]}
            ids       = raw["ids"][0]
            metadatas = raw["metadatas"][0]
            distances = raw["distances"][0]   # cosine distance ∈ [0, 2]，The smaller, the more similar

            results = []
            for doc_id, meta, dist in zip(ids, metadatas, distances):  
                score = 1.0 - dist
                if score < score_threshold:
                    continue
                doc = Document(
                    page_content="",   # Text is filled back by TextHydrationStage
                    metadata=meta,
                )
                results.append((doc, score))

            results.sort(key=lambda x: x[1], reverse=True)
            return results
        except Exception as e:
            logger.exception(f"Search failed: {e}")
            return []
        
    def as_retriever(
        self,
        kb_id:           int,
        top_k:           int            = 10,
        score_threshold: float          = 0.5,
        metadata_filter: Optional[dict] = None,
    ) -> "VectorStoreRetriever":
        """
        Factory method — returns a LangChain BaseRetriever bound to this manager.

        Args:
            kb_id:           Target knowledge base ID.
            top_k:           Maximum number of results to return.
            score_threshold: Minimum cosine similarity score (0-1).
            metadata_filter: Optional Chroma metadata filter dict.

        Returns:
            VectorStoreRetriever — drop-in BaseRetriever for any LangChain chain.
        """
        return VectorStoreRetriever(
            vs_manager      = self,
            kb_id           = kb_id,
            top_k           = top_k,
            score_threshold = score_threshold,
            metadata_filter = metadata_filter,
        )
    

# ==========================================================
# LangChain Retriever Adapter
# ==========================================================

class VectorStoreRetriever(BaseRetriever):
    """
    LangChain-compatible retriever backed by VectorStoreManager.

    Wraps a VectorStoreManager instance so it can be plugged directly into
    any LangChain pipeline that accepts a BaseRetriever
    (RetrievalQA, ConversationalRetrievalChain, LCEL | operator, etc.).

    Example
    -------
    ::

        vsm = VectorStoreManager(...)
        retriever = vsm.as_retriever(
            kb_id=1,
            top_k=10,
            score_threshold=0.6,
            metadata_filter={"doc_id": {"$in": [3, 7]}},
        )

        # LCEL
        chain = retriever | some_llm

        # RetrievalQA
        qa = RetrievalQA.from_chain_type(llm=llm, retriever=retriever)
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    vs_manager:      VectorStoreManager = Field(..., exclude=True)
    kb_id:           int
    top_k:           int                = 10
    score_threshold: float              = 0.5
    metadata_filter: Optional[dict]     = None

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> List[Document]:
        """
        Called by LangChain internals for every retrieval request.
        Returns a plain list of Document objects (page_content + metadata).
        """
        pairs = self.vs_manager.similarity_search(
            kb_id           = self.kb_id,
            query           = query,
            top_k           = self.top_k,
            score_threshold = self.score_threshold,
            metadata_filter = self.metadata_filter,
        )
        # Attach retrieval score to metadata so downstream steps can use it
        docs = []
        for doc, score in pairs:
            doc.metadata["retrieval_score"] = round(score, 4)
            doc.metadata["retrieval_type"]  = "vector"
            docs.append(doc)
        return docs
    
# ==========================================================
# 测试用例
# ==========================================================
def test_vector_store_manager():
    """
    完整的VectorStoreManager测试用例，包含：
    1. 初始化测试
    2. 添加chunk测试
    3. 重复添加去重测试
    4. 相似性搜索测试
    5. 按doc_id删除测试
    6. 按chunk_id删除测试
    7. 删除集合测试
    """
    from app.infra.db.database import Chunk as MockChunk

    test_kb_id  = 999   # 测试用KB ID
    test_doc_id = 1001  # 测试用文档ID
    ollama_base_url = "http://localhost:11434"  # 请确保本地Ollama服务已启动

    # 1. 初始化管理器
    logger.info("=== 测试1: 初始化VectorStoreManager ===")
    vsm = VectorStoreManager(
        db_path="./data/test_vector_chroma",   # 目录路径（非 .db 文件）
        ollama_base_url=ollama_base_url,
        embed_model="quentinz/bge-large-zh-v1.5"
    )
    
    # 清理上次测试残留
    vsm.drop_collection(kb_id=test_kb_id)
    
    # 2. 构建测试Chunk并添加
    logger.info("=== 测试2: 添加测试Chunk ===")
    test_chunks = [
        MockChunk(id=1, doc_id=test_doc_id, text="人工智能（AI）是模拟人类智能的技术。"),
        MockChunk(id=2, doc_id=test_doc_id, text="大语言模型是AI的重要分支，例如LLaMA、GPT。"),
        MockChunk(id=3, doc_id=1002,        text="Chroma是一款开源的向量数据库，专为相似性搜索设计。")
    ]

    def batch_callback(done, total):
        logger.info(f"添加进度: {done}/{total}")

    vsm.add_chunks(
        kb_id=test_kb_id,
        chunks=test_chunks,
        embed_batch_size=2,
        on_batch=batch_callback
    )
    assert test_kb_id in vsm._stores, "添加Chunk后应创建测试KB的store"

    # 3. 测试重复添加（应跳过）
    logger.info("=== 测试3: 重复添加相同Chunk（应跳过） ===")
    vsm.add_chunks(kb_id=test_kb_id, chunks=test_chunks)
    store = vsm._get_store(test_kb_id)
    existing_ids = vsm._get_existing_ids(store, [1, 2, 3])
    assert existing_ids == {1, 2, 3}, "重复添加后应仍只有3个Chunk"
    

    # 4. 相似性搜索测试（无过滤）
    logger.info("=== 测试4: 相似性搜索（无过滤） ===")
    results = vsm.similarity_search(
        kb_id=test_kb_id,
        query="大语言模型属于AI的哪类技术？",
        top_k=2,
        score_threshold=0.5
    )
    assert len(results) >= 1, "搜索结果应至少包含1条相关内容"
    result_texts = [doc.page_content for doc, score in results]
    assert any("大语言模型" in t for t in result_texts), "搜索结果应包含相关文本"
    logger.info(f"搜索结果示例: {results[0][0].page_content} (相似度: {results[0][1]:.4f})")

    # 4a. metadata_filter 单字段等值过滤
    logger.info("=== 测试4a: metadata_filter 单字段等值过滤 ===")
    results_filtered = vsm.similarity_search(
        kb_id=test_kb_id,
        query="大语言模型属于AI的哪类技术？",
        top_k=3,
        score_threshold=0.0,
        metadata_filter={"doc_id": test_doc_id},
    )
    assert all(
        doc.metadata[VectorStoreManager.DOC_ID_FIELD] == test_doc_id
        for doc, _ in results_filtered
    ), "过滤后结果应全部属于 test_doc_id"
    logger.info(f"metadata_filter 过滤结果数: {len(results_filtered)}")

    # 4b. metadata_filter 操作符过滤（$in）
    logger.info("=== 测试4b: metadata_filter $in 操作符过滤 ===")
    results_in = vsm.similarity_search(
        kb_id=test_kb_id,
        query="向量数据库",
        top_k=3,
        score_threshold=0.0,
        metadata_filter={"doc_id": {"$in": [1002]}},
    )
    assert all(
        doc.metadata[VectorStoreManager.DOC_ID_FIELD] == 1002
        for doc, _ in results_in
    ), "$in 过滤后结果应全部属于 doc_id=1002"
    logger.info(f"$in 过滤结果数: {len(results_in)}")

    # 4c. 复杂逻辑直接传原生 Chroma where dict（$or）
    logger.info("=== 测试4c: 原生 $or 过滤 ===")
    results_or = vsm.similarity_search(
        kb_id=test_kb_id,
        query="人工智能技术",
        top_k=3,
        score_threshold=0.0,
        metadata_filter={"$or": [
            {"doc_id": {"$eq": test_doc_id}},
            {"doc_id": {"$eq": 1002}},
        ]},
    )
    assert len(results_or) >= 1, "$or 过滤应能返回结果"
    logger.info(f"$or 过滤结果数: {len(results_or)}")

    # 4d. 单元测试 _build_where 逻辑
    logger.info("=== 测试4d: _build_where 单元测试 ===")
    bw = VectorStoreManager._build_where
    assert bw(None) is None
    assert bw({"doc_id": 42}) == {"doc_id": {"$eq": 42}}
    assert bw({"doc_id": {"$in": [1, 2]}}) == {"doc_id": {"$in": [1, 2]}}
    multi = bw({"doc_id": 42, "section": "intro"})
    assert "$and" in multi and len(multi["$and"]) == 2
    passthrough = bw({"$or": [{"doc_id": 1}, {"doc_id": 2}]})
    assert passthrough == {"$or": [{"doc_id": 1}, {"doc_id": 2}]}
    logger.info("_build_where 单元测试全部通过")
    
    store = vsm._get_store(test_kb_id)
    # 5. 按doc_id删除测试
    logger.info("=== 测试5: 按doc_id删除 ===")
    vsm.delete_by_doc_id(kb_id=test_kb_id, doc_id=test_doc_id)
    existing_ids = vsm._get_existing_ids(store, [1, 2])
    assert existing_ids == set(), "删除doc_id后应不存在对应Chunk"
    existing_ids = vsm._get_existing_ids(store, [3])
    assert existing_ids == {3}, "未删除的doc_id对应Chunk应仍存在"

    # 6. 按chunk_id删除测试
    logger.info("=== 测试6: 按chunk_id删除 ===")
    vsm.delete_by_chunk_ids(kb_id=test_kb_id, chunk_ids=[3])
    existing_ids = vsm._get_existing_ids(store, [3])
    assert existing_ids == set(), "按chunk_id删除后应不存在对应Chunk"

    # 7. 删除集合测试
    logger.info("=== 测试7: 删除整个KB集合 ===")
    vsm.drop_collection(kb_id=test_kb_id)
    assert test_kb_id not in vsm._stores, "删除集合后应从缓存中移除store"

    logger.info("=== 所有测试用例执行完成 ===")


if __name__ == "__main__":
    logger.add(
        sink=lambda msg: print(msg, end=""),
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    )

    try:
        test_vector_store_manager()
    except Exception as e:
        logger.error(f"测试执行失败: {e}")
        raise
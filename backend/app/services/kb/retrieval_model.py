#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-29
# @description: Retrieval model.

from dataclasses import dataclass,field
from typing import Any,Optional,Dict,List
from langchain_core.documents import Document
from pydantic import BaseModel,Field

from app.retrieval.reranker.base import Scorable

class QueryRequest(BaseModel):
    query: str = Field(..., description="The questions of user.")
    metadata_filter: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional: Metadata conditions for filtering documents",
    )

@dataclass
class RetrievedChunk(Scorable):
    """
    Unified retrieval result that flows through every pipeline stage.

    Fields
    ------
    chunk_id        SQLite Chunk.id
    doc_id          SQLite Document.id
    kb_id           Knowledge-base id
    text            Chunk text (child chunk, or expanded parent after S2B stage)
    vector_score    Cosine similarity from Chroma   (None if not vector-retrieved)
    bm25_score      BM25/TF score                   (None if not BM25-retrieved)
    rrf_score       Reciprocal Rank Fusion score     (set by FusionStage)
    rerank_score    External reranker score          (set by RerankStage)
    final_score     Score used for final ordering — the last stage writes this
    metadata        Arbitrary extra fields (source, page, content_type ...)
    retrieval_path  Audit trail of contributing stages, e.g. ["vector","rrf","s2b"]
    """
    chunk_id:       Any
    doc_id:         int
    kb_id:          int
    text:           str
    vector_score:   Optional[float] = None
    bm25_score:     Optional[float] = None
    rrf_score:      Optional[float] = None
    rerank_score:   Optional[float] = None
    final_score:    float           = 0.0
    metadata:       Dict[str, Any]  = field(default_factory=dict)
    retrieval_path: List[str]       = field(default_factory=list)

    def to_langchain_document(self) -> Document:
        meta = {
            **self.metadata,
            "chunk_id":       self.chunk_id,
            "doc_id":         self.doc_id,
            "kb_id":          self.kb_id,
            "final_score":    round(self.final_score, 4),
            "retrieval_path": ",".join(self.retrieval_path),
        }
        if self.vector_score is not None:
            meta["vector_score"]  = round(self.vector_score, 4)
        if self.bm25_score is not None:
            meta["bm25_score"]    = round(self.bm25_score, 4)
        if self.rrf_score is not None:
            meta["rrf_score"]     = round(self.rrf_score, 4)
        if self.rerank_score is not None:
            meta["rerank_score"]  = round(self.rerank_score, 4)
        return Document(page_content=self.text, metadata=meta)

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict for cache storage."""
        return {
            "chunk_id":       self.chunk_id,
            "doc_id":         self.doc_id,
            "kb_id":          self.kb_id,
            "text":           self.text,
            "vector_score":   self.vector_score,
            "bm25_score":     self.bm25_score,
            "rrf_score":      self.rrf_score,
            "rerank_score":   self.rerank_score,
            "final_score":    self.final_score,
            "metadata":       self.metadata,
            "retrieval_path": self.retrieval_path,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RetrievedChunk":
        """Deserialize from a cached dict."""
        return cls(
            chunk_id       = d["chunk_id"],
            doc_id         = d["doc_id"],
            kb_id          = d["kb_id"],
            text           = d["text"],
            vector_score   = d.get("vector_score"),
            bm25_score     = d.get("bm25_score"),
            rrf_score      = d.get("rrf_score"),
            rerank_score   = d.get("rerank_score"),
            final_score    = d.get("final_score", 0.0),
            metadata       = d.get("metadata", {}),
            retrieval_path = d.get("retrieval_path", []),
        )
    
@dataclass
class ChunkResult:
    """Single retrieved chunk returned by the query pipeline."""
    chunk_id:       Any
    doc_id:         int
    kb_id:          int
    text:           str
    final_score:    float
    vector_score:   Optional[float] = None
    bm25_score:     Optional[float] = None
    rrf_score:      Optional[float] = None
    rerank_score:   Optional[float] = None
    retrieval_path: List[str]       = field(default_factory=list)
    metadata:       Dict[str, Any]  = field(default_factory=dict)

@dataclass
class KBInfo:
    name:str
    keywords:Optional[Dict]
    description:Optional[str]
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-22
# @description: reranker base class.

from abc import ABC, abstractmethod
from typing import List
import asyncio
from enum import Enum

# ═══════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════

class RerankMode(str, Enum):
    """
    Controls how the final result list is scored and ordered.

    score  — rank by original DuckDuckGo position (no model call, fastest)
    bge    — BGEReranker with pluggable backend: local / remote / ollama
    llm    — call LLM to score each result (most accurate, slowest)
    """
    SCORE = "score"
    BGE   = "bge"
    LLM   = "llm"

class Scorable(ABC):
    """
    Structural protocol satisfied by any object that carries scorable text.

    Both RetrievedChunk (retrieval.py) and the _Stub dataclass inside
    LLMRerankerAdapter (web_search.py) satisfy this protocol, so the same
    LLMReranker / LLMBatchReranker implementation serves both pipelines
    without modification.

    Fields written by the reranker
    ───────────────────────────────
    final_score    ← primary sort key, used by RerankStage in both pipelines
    rerank_score   ← raw model output (same value as final_score here)
    retrieval_path ← list of string tags; the reranker appends "llm"
    """

    text : str
    final_score:    float
    rerank_score:   float
    retrieval_path: List[str]

class BaseReranker(ABC):
    """
    Pluggable reranker interface.
    Implement this to add a cross-encoder, Cohere reranker, or similar.

    Contract
    --------
    - Must set rc.rerank_score and rc.final_score on every returned chunk.
    - Must return at most top_k items, sorted by final_score descending.
    """
    @abstractmethod
    async def rerank(
        self,
        query:  str,
        chunks: List[Scorable],
        top_k:  int,
    ) -> List[Scorable]:
        ...

class BaseLLMReranker(BaseReranker, ABC):
    """
    Convenience base for LLM-based rerankers.

    Subclasses implement only score_one(query, text) -> float [0,1].
    The base class handles parallel scoring, final_score assignment,
    path tagging, and top_k truncation uniformly.
    """
    @abstractmethod
    async def score_one(self, query: str, text: str) -> float:
        """Return a relevance score in [0,1]. Higher = more relevant."""

    async def rerank(
        self,
        query:  str,
        chunks: List[Scorable],
        top_k:  int,
    ) -> List[Scorable]:
        scores: List[float] = await asyncio.gather(
            *[self.score_one(query, rc.text) for rc in chunks]
        )
        for rc, score in zip(chunks, scores):
            rc.rerank_score = score
            rc.final_score  = score
            if "llm" not in rc.retrieval_path:
                rc.retrieval_path.append("llm")
        chunks.sort(key=lambda rc: rc.final_score, reverse=True)
        return chunks[:top_k]



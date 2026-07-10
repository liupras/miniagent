#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-13
# @description: Retrieval pipeline — dynamically assembled from StrategyConfig.


from __future__ import annotations

import asyncio
import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from langchain_core.stores import BaseStore
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from loguru import logger
from pydantic import ConfigDict, Field

from ...retrieval.vector_store import VectorStoreManager
from ...infra.search.bm25_manager import BM25Manager
from .retrieval_model import RetrievedChunk
from .citation_merger import CitationMerger

from app.infra.db.database import StrategyConfig,LLM
from app.repositories import AsyncParentChunkDatabase, AsyncChunkDatabase, AsyncDocumentDatabase
from app.runtime.llm.client import LLMClient
from app.infra.cache.factory import create_cache_backend
from app.retrieval.reranker.base import RerankMode
from app.retrieval.reranker.factory import RerankerFactory
from app.retrieval.adaptive_threshold import AdaptiveThresholdMixin


# ═══════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════

class KBRankingMode(str, Enum):
    """
    Controls how the final result list is scored and ordered.

    vector  — rank by cosine similarity score only (no BM25, no reranker)
    bm25    — rank by BM25/TF score only           (no vector, no reranker)
    hybrid  — rank by fusion score from FusionStage (rrf or weighted)
    rerank  — hand off to an external cross-encoder / Cohere reranker
    llm     — call an LLM to score each chunk for relevance (slowest, most accurate)
    """
    VECTOR = "vector"
    BM25   = "bm25"
    HYBRID = "hybrid"
    RERANK = "rerank"
    LLM    = "llm"  # Not yet tested

class FusionMode(str, Enum):
    RRF      = "rrf"
    WEIGHTED = "weighted"

# =========================================================
# Pipeline State
# =========================================================

@dataclass
class PipelineState:
    """
    Shared state flowing through the pipeline.
    """

    # input
    original_query: str
    metadata_filter: Optional[dict] = None

    # query transform
    queries: List[str] = field(default_factory=list)

    # retrieval results
    vector_chunks: List = field(default_factory=list)
    bm25_chunks: List = field(default_factory=list)

    # merged results
    chunks: List = field(default_factory=list)

    # final output
    confidence = None

    # The dynamic top_k for each request is independent and written by AdaptiveTopKStage.
    vector_top_k:    Optional[int]  = None
    bm25_top_k:      Optional[int]  = None


# ═══════════════════════════════════════════════════════════════════════════
# Base Stage
# ═══════════════════════════════════════════════════════════════════════════

class BaseStage(ABC):
    """A single, composable retrieval stage."""

    @abstractmethod
    async def run(self, state: PipelineState) -> PipelineState:
        raise NotImplementedError

class BaseQueryStage(ABC):
    """
    Query transformation stage.
    Input:  query
    Output: query or list[query]
    """

    @abstractmethod
    async def run(self, query: str) -> List[str]:
        ...

# ═══════════════════════════════════════════════════════════════════════════
# Stage 1.1 - Query Transformation -> Query rewrite
# ═══════════════════════════════════════════════════════════════════════════
class QueryRewriteStage(BaseQueryStage):
    """
    Rewrite the user query to improve retrieval quality.
    """

    def __init__(self, llm_client: LLMClient, model: str, prompt_template: str):
        self.llm           = llm_client
        self.model         = model
        self._prompt_template = prompt_template

    async def run(self, query: str) -> List[str]:
        
        prompt   = self._prompt_template.format_map({"query": query})

        resp = await self.llm.achat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )

        new_query = resp.content.strip()

        logger.debug(f"[QueryRewrite] {query} → {new_query}")

        return [new_query]

# ═══════════════════════════════════════════════════════════════════════════
# Stage 1.2 - Query Transformation -> Query expansion
# ═══════════════════════════════════════════════════════════════════════════
class QueryExpansionStage(BaseQueryStage):
    """
    Generate multiple retrieval queries.
    """

    def __init__(
        self,
        llm_client:    LLMClient,
        model:         str,
        prompt_template: str,
        expansion_num: int = 3,
    ):
        self.llm           = llm_client
        self.model         = model
        self._prompt_template = prompt_template
        self.expansion_num = expansion_num

    async def run(self, query: str) -> List[str]:
        
        prompt   = self._prompt_template.format_map({"query": query, "expansion_num": self.expansion_num})

        resp = await self.llm.achat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )

        queries = [
            q.strip()
            for q in resp.content.split("\n")
            if q.strip()
        ]

        logger.debug(f"[QueryExpansion] {len(queries)} queries")

        return queries

# ═══════════════════════════════════════════════════════════════════════════
# Stage 1.3 - Query Transformation -> Hypothetical Document Embedding
# ═══════════════════════════════════════════════════════════════════════════
class HyDEStage(BaseQueryStage):
    """
    Hypothetical Document Embedding (HyDE).
    """

    def __init__(self, llm: LLMClient, model: str, prompt_template: str):
        self.llm           = llm
        self.model         = model
        self._prompt_template = prompt_template

    async def run(self, query: str) -> List[str]:
        
        prompt   = self._prompt_template.format_map({"query": query})

        resp = await self.llm.achat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )

        hypothetical_doc = resp.content.strip()

        logger.debug(
            f"[HyDE] generated hypothetical doc len={len(hypothetical_doc)}"
        )

        return [hypothetical_doc]

# ═══════════════════════════════════════════════════════════════════════════
# Stage 1 - Query Transformation
# ═══════════════════════════════════════════════════════════════════════════
class QueryTransformStage(BaseStage):

    def __init__(
            self,
            query_transforms: List[BaseQueryStage],
            max_queries: int = 5,
        ):

        self.query_transforms = query_transforms
        self.max_queries = max_queries

    async def run(self, state: PipelineState) -> PipelineState:

        queries = [state.original_query]

        for query_transform in self.query_transforms:
            new_query = await query_transform.run(query=state.original_query)
            queries.extend(q for q in new_query if q)

        # ---------- Deduplication ----------
        queries = list(dict.fromkeys(queries))

        # ---------- Maximum quantity limit ----------
        if len(queries) > self.max_queries:
            queries = queries[:self.max_queries]

        state.queries = queries

        logger.debug(f"[QueryTransform] final queries={len(queries)}")

        return state

# ═══════════════════════════════════════════════════════════════════════════
# Stage 2 - AdaptiveTop
# ═══════════════════════════════════════════════════════════════════════════
class AdaptiveTopKStage(BaseStage):
    """
    Dynamically adjust retrieval top_k based on query complexity.
    """

    def __init__(
        self,        
        base_vector_topk: int = 20,
        base_bm25_topk:   int = 20,
        max_scale: float = 2.0,
    ):        
        self.base_vector_topk = base_vector_topk
        self.base_bm25_topk   = base_bm25_topk
        self.max_scale        = max_scale

    def _estimate_complexity(self, query: str) -> float:

        length = len(query)

        if length < 20:
            return 0.7

        if length < 60:
            return 1.0

        if length < 120:
            return 1.3

        return 1.6

    async def run(self, state: PipelineState):

        query = state.original_query

        factor = min(self._estimate_complexity(query), self.max_scale)
        state.vector_top_k = int(self.base_vector_topk * factor)
        state.bm25_top_k   = int(self.base_bm25_topk   * factor)
        logger.debug(
            f"[AdaptiveTopK] factor={factor} "
            f"vector_topk={state.vector_top_k} bm25_topk={state.bm25_top_k}"
        )
        return state


class BaseRetrievalStage(ABC):
    """
    Retrieval stage.
    Input:  query
    Output: List[RetrievedChunk]
    """

    @abstractmethod
    async def run(self, query: str,metadata_filter: Optional[dict] = None) -> List[RetrievedChunk]:
        ...

# ═══════════════════════════════════════════════════════════════════════════
# Stage 3.1 - RetrievalStage -> Vector retrieval
# ═══════════════════════════════════════════════════════════════════════════

class VectorStage(BaseStage):
    """Dense vector retrieval via Chroma."""

    def __init__(
        self,
        vs_manager:      VectorStoreManager,
        kb_id:           int,
        default_top_k:           int,
        score_threshold: float
    ):
        self.vs_manager      = vs_manager
        self.kb_id           = kb_id
        self.default_top_k   = default_top_k
        self.score_threshold = score_threshold        

    async def run(self, query: str,
                  metadata_filter: Optional[dict] = None,
                  top_k:           Optional[int]  = None,   # Passed by RetrievalStage
                  ) -> List[RetrievedChunk]:
        
        effective_top_k = top_k if top_k is not None else self.default_top_k
        results = await asyncio.to_thread(
            self.vs_manager.similarity_search,
            kb_id           = self.kb_id,
            query           = query,
            top_k           = effective_top_k,
            score_threshold = self.score_threshold,
            metadata_filter = metadata_filter,
        )

        chunks = []
        for doc, score in results:
            meta = doc.metadata or {}
            chunk = RetrievedChunk(
                chunk_id     = meta.get("chunk_db_id"),
                doc_id       = meta.get("doc_id", 0),
                kb_id        = self.kb_id,
                text         = "",           # filled later by TextHydrationStage
                vector_score = score,
                final_score  = score,
                metadata     = meta,
                retrieval_path = ["vector"],
            )
            chunks.append(chunk)

        logger.debug(f"[VectorStage] kb={self.kb_id}  retrieved={len(chunks)}")
        return chunks


# ═══════════════════════════════════════════════════════════════════════════
# Stage 3.2 - RetrievalStage -> BM25 retrieval
# ═══════════════════════════════════════════════════════════════════════════

class BM25Stage(BaseStage):
    """Sparse BM25 retrieval."""

    def __init__(
        self,
        bm25_manager:    BM25Manager,
        kb_id:           int,
        default_top_k:           int,
        score_threshold: float,
    ):
        self.bm25_manager    = bm25_manager
        self.kb_id           = kb_id
        self.default_top_k   = default_top_k
        self.score_threshold = score_threshold

    async def run(self, query: str,
                  metadata_filter: Optional[dict] = None,
                  top_k:           Optional[int]  = None,   # Passed by RetrievalStage
                  ) -> List[RetrievedChunk]:
        effective_top_k = top_k if top_k is not None else self.default_top_k
        results = self.bm25_manager.search(
            kb_id           = str(self.kb_id),
            query           = query,
            top_k           = effective_top_k,
            score_threshold = self.score_threshold,
        )

        chunks = []
        for item in results:
            meta = item.get("metadata", {})
            chunk = RetrievedChunk(
                chunk_id     = item["id"],
                doc_id       = meta.get("doc_id", 0),
                kb_id          = self.kb_id,
                text           = item.get("text", ""),
                bm25_score     = item["score"],
                final_score    = item["score"],
                metadata       = item.get("metadata", {}),
                retrieval_path = ["bm25"],
            )
            chunks.append(chunk)

        logger.debug(f"[BM25Stage] kb={self.kb_id}  retrieved={len(chunks)}")
        return chunks


# ═══════════════════════════════════════════════════════════════════════════
# Stage 3 - RetrievalStage (parallel dispatch)
# ═══════════════════════════════════════════════════════════════════════════

class RetrievalStage(BaseStage):

    def __init__(
        self,
        vector_stage: VectorStage,
        bm25_stage:   BM25Stage,
    ):
        self.vector_stage = vector_stage
        self.bm25_stage   = bm25_stage

    async def run(self, state: PipelineState) -> PipelineState:

        tasks = []
        sources = []

        if not state.queries:
            state.queries = [state.original_query]

        for q in state.queries:

            if self.vector_stage:
                tasks.append(self.vector_stage.run(q,
                    metadata_filter = state.metadata_filter,
                    top_k = state.vector_top_k))
                sources.append("vector")

            if self.bm25_stage:
                tasks.append(self.bm25_stage.run(q,
                    metadata_filter = state.metadata_filter,
                    top_k = state.bm25_top_k))
                sources.append("bm25")

        results = await asyncio.gather(*tasks)

        for src, result in zip(sources, results):
            if src == "vector":
                state.vector_chunks.extend(result)
            else:
                state.bm25_chunks.extend(result)

        state.vector_chunks = deduplicate_chunks(state.vector_chunks)
        state.bm25_chunks   = deduplicate_chunks(state.bm25_chunks)

        return state


# ═══════════════════════════════════════════════════════════════════════════
# Stage 4 - Fusion  (RRF or weighted)
# ═══════════════════════════════════════════════════════════════════════════

class FusionStage(BaseStage):
    """
    Merge results from VectorStage and BM25Stage into a single ranked list.

    Modes
    -----
    FusionMode.RRF      Reciprocal Rank Fusion (rank-based, scale-invariant).
                        Score = sum(1 / (k + rank_i)) across contributing lists.

    FusionMode.WEIGHTED Min-max normalise each list to [0,1], then combine:
                        score = alpha * vector_norm + (1 - alpha) * bm25_norm
                        alpha = vector_weight (default 0.6, from extra_config)

    After fusion, rrf_score (RRF) or final_score (weighted) is set on every
    chunk and all score fields are merged so downstream stages see everything.
    """

    def __init__(
        self,
        mode:          FusionMode = FusionMode.RRF,
        rrf_k:         int        = 60,
        vector_weight: float      = 0.6,
        rrf_top_k:     int        = 20
    ):
        self.mode          = mode
        self.rrf_k         = rrf_k
        self.vector_weight = vector_weight
        self.rrf_top_k     = rrf_top_k

    async def run(self, state: PipelineState) -> PipelineState:
        if not state.bm25_chunks:
            state.chunks = state.vector_chunks[:self.rrf_top_k]
            return state

        if not state.vector_chunks:
            state.chunks = state.bm25_chunks[:self.rrf_top_k]
            return state

        merged = (
            self._weighted_merge(state)
            if self.mode == FusionMode.WEIGHTED
            else self._rrf_merge(state)
        )
        logger.debug(
            f"[FusionStage] mode={self.mode.value}  "
            f"vector={len(state.vector_chunks)}  bm25={len(state.bm25_chunks)}  "
            f"merged={len(merged)}"
        )

        state.chunks = merged[:self.rrf_top_k]
        return state

    def _rrf_merge(self, state: PipelineState) -> List[RetrievedChunk]:
        k = self.rrf_k

        def rank_map(lst: List[RetrievedChunk]) -> Dict[Any, int]:
            return {rc.chunk_id: i + 1 for i, rc in enumerate(lst)}

        v_rank = rank_map(state.vector_chunks)
        b_rank = rank_map(state.bm25_chunks)

        registry: Dict[Any, RetrievedChunk] = {}
        for rc in state.vector_chunks:
            registry[rc.chunk_id] = rc
        for rc in state.bm25_chunks:
            if rc.chunk_id not in registry:
                registry[rc.chunk_id] = rc
            else:
                existing = registry[rc.chunk_id]
                existing.bm25_score = rc.bm25_score
                if "bm25" not in existing.retrieval_path:
                    existing.retrieval_path.append("bm25")
                # Vector chunks don't have text, while BM25 does; they can be reused directly.
                if not existing.text and rc.text:
                    existing.text = rc.text

        for chunk_id, rc in registry.items():
            rrf = 0.0
            if chunk_id in v_rank:
                rrf += 1.0 / (k + v_rank[chunk_id])
            if chunk_id in b_rank:
                rrf += 1.0 / (k + b_rank[chunk_id])
            rc.rrf_score   = rrf
            rc.final_score = rrf
            if "rrf" not in rc.retrieval_path:
                rc.retrieval_path.append("rrf")

        return sorted(registry.values(), key=lambda rc: rc.final_score, reverse=True)

    def _weighted_merge(self, state: PipelineState) -> List[RetrievedChunk]:
        alpha = self.vector_weight

        def _minmax(scores: List[float]) -> List[float]:
            lo, hi = min(scores, default=0.0), max(scores, default=1.0)
            span = hi - lo or 1.0
            return [(s - lo) / span for s in scores]

        v_norm = _minmax([rc.vector_score or 0.0 for rc in state.vector_chunks])
        b_norm = _minmax([rc.bm25_score   or 0.0 for rc in state.bm25_chunks])

        registry: Dict[Any, RetrievedChunk] = {}
        for rc, ns in zip(state.vector_chunks, v_norm):
            rc._v_norm = ns
            registry[rc.chunk_id] = rc
        for rc, ns in zip(state.bm25_chunks, b_norm):
            rc._b_norm = ns
            if rc.chunk_id not in registry:
                rc._v_norm = 0.0
                registry[rc.chunk_id] = rc
            else:
                existing = registry[rc.chunk_id]
                existing._b_norm    = ns
                existing.bm25_score = rc.bm25_score
                if "bm25" not in existing.retrieval_path:
                    existing.retrieval_path.append("bm25")
                # Vector chunks don't have text, while BM25 does; they can be reused directly.
                if not existing.text and rc.text:
                    existing.text = rc.text

        for rc in registry.values():
            v = getattr(rc, "_v_norm", 0.0)
            b = getattr(rc, "_b_norm", 0.0)
            rc.final_score = alpha * v + (1 - alpha) * b
            if "weighted" not in rc.retrieval_path:
                rc.retrieval_path.append("weighted")

        return sorted(registry.values(), key=lambda rc: rc.final_score, reverse=True)


# ═══════════════════════════════════════════════════════════════════════════
# Stage 5 - Small-to-Big expansion
# ═══════════════════════════════════════════════════════════════════════════

class SmallToBigStage(BaseStage):
    """
    Replace each child-chunk's text with its parent ParentChunk text.

    De-duplicates by parent_id: when multiple children share the same parent,
    the child with the highest final_score wins and represents that parent.
    All score fields from the winning child are preserved unchanged.
    """

    def __init__(self, pc_db: AsyncParentChunkDatabase, kb_id: int):
        self.pc_db = pc_db
        self.kb_id = kb_id

    async def run(self, state: PipelineState) -> PipelineState:
        if not state.chunks:
            return state

        parent_ids = {
            rc.metadata.get("parent_id")
            for rc in state.chunks
            if rc.metadata.get("parent_id") is not None
        }
        if not parent_ids:
            logger.debug("[S2BStage] No parent_id in metadata - skipping")
            return state

        parent_map = await self._load_parents(parent_ids=list(parent_ids))

        seen_parents: Dict[int, RetrievedChunk] = {}
        no_parent:    List[RetrievedChunk]      = []

        for rc in state.chunks:
            pid = rc.metadata.get("parent_id")
            if pid is None or pid not in parent_map:
                no_parent.append(rc)
                continue
            if pid not in seen_parents or rc.final_score > seen_parents[pid].final_score:
                seen_parents[pid] = RetrievedChunk(
                    chunk_id       = rc.chunk_id,
                    doc_id         = rc.doc_id,
                    kb_id          = rc.kb_id,
                    text           = parent_map[pid],
                    vector_score   = rc.vector_score,
                    bm25_score     = rc.bm25_score,
                    rrf_score      = rc.rrf_score,
                    rerank_score   = rc.rerank_score,
                    final_score    = rc.final_score,
                    metadata       = {**rc.metadata, "expanded": True},
                    retrieval_path = rc.retrieval_path + ["s2b"],
                )

        result = sorted(
            list(seen_parents.values()) + no_parent,
            key=lambda rc: rc.final_score,
            reverse=True,
        )
        logger.debug(f"[S2BStage] {len(state.chunks)} child -> {len(result)} expanded")

        state.chunks = result
        return state

    async def _load_parents(self, parent_ids: List[int]) -> Dict[int, str]:
        return await self.pc_db.get_texts_by_ids(parent_ids)

# ═══════════════════════════════════════════════════════════════════════════
# Stage 6 - TextHydration
# ═══════════════════════════════════════════════════════════════════════════

class TextHydrationStage(BaseStage):
    """
    Lazy-loaded text completion stage at the end of the pipeline.

    Batch back-query SQLite only for RetrievedChunks with empty text,
    Avoiding line-by-line queries within VectorStage, maximizing the reuse of existing text from BM25/S2B.
    """

    def __init__(self, chunk_db: AsyncChunkDatabase):
        """
        Args:
            chunk_db: Provides an SQLite access object for get_texts_by_ids(ids) -> Dict[int, str].
        """
        self.chunk_db = chunk_db

    async def run(self, state: PipelineState) -> PipelineState:
        # Find all chunks with empty text.
        missing = [rc for rc in state.chunks if not rc.text]
        if not missing:
            return state  # All existing text will be skipped (BM25 and S2B are both covered).

        # Batch query SQLite, one IN query
        missing_ids = [rc.chunk_id for rc in missing]
        text_map: Dict[int, str] = await self.chunk_db.get_texts_by_ids(chunk_ids = missing_ids)

        filled = 0
        for rc in missing:
            t = text_map.get(rc.chunk_id)
            if t:
                rc.text = t
                rc.retrieval_path = rc.retrieval_path + ["hydra"]
                filled += 1
            else:
                logger.warning(
                    f"[HydrationStage] chunk_id={rc.chunk_id} not found in SQLite"
                )

        logger.debug(
            f"[HydrationStage] missing={len(missing)}  filled={filled}  "
            f"skipped={len(state.chunks) - len(missing)} (already had text)"
        )
        return state

# ═══════════════════════════════════════════════════════════════════════════
# Stage 7 - Rerank (mode-aware)
# ═══════════════════════════════════════════════════════════════════════════

class RerankStage(BaseStage):
    """
    Final scoring stage — behaviour is fully determined by KBRankingMode.

    KBRankingMode.VECTOR  Re-sort by vector_score. Chunks with no vector score
                        are pushed to the end. Sets final_score = vector_score.

    KBRankingMode.BM25    Re-sort by bm25_score.   Same fallback rule.
                        Sets final_score = bm25_score.

    KBRankingMode.HYBRID  Keep the fusion score already on final_score (no-op sort).
                        Useful when Fusion already produced the desired order.

    KBRankingMode.RERANK  Delegate to a BaseReranker implementation.
                        Requires reranker != None; falls back to HYBRID with a
                        warning if missing, so production is never blocked.

    KBRankingMode.LLM     Delegate to a BaseLLMReranker implementation.
                        Requires reranker to be BaseLLMReranker; falls back to
                        RERANK, then HYBRID if still unresolvable.

    In all modes, only the top_k results are returned.
    """

    def __init__(
        self,
        mode:     KBRankingMode,        
        reranker: RerankerFactory,
    ):
        self._mode     = mode
        self._reranker = reranker

    async def run(self, state: PipelineState) -> PipelineState:
        if not state.chunks:
            return state  

        if self._mode == KBRankingMode.VECTOR:
            for rc in state.chunks:
                s = getattr(rc, "vector_score") or 0  
                rc.final_score = s
        elif self._mode == KBRankingMode.BM25:
            for rc in state.chunks:
                s = getattr(rc, "bm25_score") or 0  
                rc.final_score = s

        result = await self._reranker.run(query=state.original_query,chunks=state.chunks)
        logger.debug(
            f"[RerankStage] mode={self._mode.value}  in={len(state.chunks)}  out={len(result)}"
        )

        state.chunks = result
        return state

# ═══════════════════════════════════════════════════════════════════════════
# Stage 8 - Adaptive Threshold
# ═══════════════════════════════════════════════════════════════════════════
class AdaptiveThresholdStage(AdaptiveThresholdMixin, BaseStage):
    """
    Adaptive score filtering using score distribution.

    Filtering logic lives in AdaptiveThresholdMixin._apply_threshold()
    (shared with web_search.py).  This class only wires state.chunks
    to the mixin and delegates to it.
    """

    def __init__(self, std_factor: float = 0.5, min_keep: int = 5):
        self._std_factor = std_factor
        self._min_keep   = min_keep

    async def run(self, state: PipelineState) -> PipelineState:
        state.chunks = self._apply_threshold(state.chunks)
        return state

# ═══════════════════════════════════════════════════════════════════════════
# Stage 9 - ContextTrim
# ═══════════════════════════════════════════════════════════════════════════
class ContextTrimStage(BaseStage):

    def __init__(self, max_chunks=5):
        self.max_chunks = max_chunks

    async def run(self, state: PipelineState):
        state.chunks = state.chunks[:self.max_chunks]
        return state

# ═══════════════════════════════════════════════════════════════════════════
# Stage 10 - Citation
# ═══════════════════════════════════════════════════════════════════════════
class CitationStage(BaseStage):
    """
    Forced citation phase: Completes document-level citation information for each RetrievedChunk.

    Article-level citation (articles, clauses, items, etc.) is pre-written to chunk.metadata["citation"] during the chunking phase.
    """

    def __init__(
            self, 
            doc_db: AsyncDocumentDatabase,
            merger: CitationMerger | None = None
        ):
        self.doc_db = doc_db
        self.merger   = merger or CitationMerger()

    async def run(self, state: PipelineState) -> PipelineState:
        if not state.chunks:
            return state

        doc_ids = list({rc.doc_id for rc in state.chunks})
        doc_map: Dict[int, dict] = await self.doc_db.get_citation_info_by_ids(doc_ids=doc_ids)
  
        for rc in state.chunks:
            doc_info = doc_map.get(rc.doc_id, {})
            merged = self.merger.merge(doc_info, rc)
            rc.metadata["citation"] = merged

        logger.debug(f"[CitationStage] annotated {len(state.chunks)} chunks")
        return state

# ═══════════════════════════════════════════════════════════════════════════
# Stage 11 - Confidence detection
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class RetrievalConfidence:
    """
    Pipeline final return result, encapsulating chunks and confidence diagnostics.

    Fields
    ------
    level    "high"  — top_score >= high_score_threshold AND high_conf_count >= min_high_conf_count
             "low"   — top_score < low_score_threshold OR high_conf_count < min_high_conf_count
             "empty" — no chunks returned
    warning  Low-confidence reminder text (None when level="high")
             Resolved via PromptLoader or StrategyConfig.confidence_warning_template;
             see ConfidenceStage for full resolution order.
    chunks   Final RetrievedChunk list, sorted by final_score descending.
    """
    level:   str
    warning: Optional[str]
    chunks:  List[RetrievedChunk]

    def to_bytes(self) -> bytes:
        """Serialize to bytes for cache storage."""
        return json.dumps({
            "level":   self.level,
            "warning": self.warning,
            "chunks":  [rc.to_dict() for rc in self.chunks],
        }, ensure_ascii=False).encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "RetrievalConfidence":
        """Deserialize from cached bytes."""
        obj = json.loads(data.decode("utf-8"))
        return cls(
            level   = obj["level"],
            warning = obj.get("warning"),
            chunks  = [RetrievedChunk.from_dict(d) for d in obj.get("chunks", [])],
        )


class ConfidenceStage(BaseStage):
    """
    Confidence detection stage.

    Rules
    -----
    - No results                                      → level="empty"
    - top_score < low_score_threshold                 → level="low"
    - high_conf_count < min_high_conf_count           → level="low"
    - Otherwise                                       → level="high"

    All parameters come from StrategyConfig / PipelineConfig:
        high_score_threshold      ← confidence_high_score_threshold  (default 0.7)
        low_score_threshold       ← confidence_low_score_threshold   (default 0.5)
        min_high_conf_count       ← confidence_min_high_conf_count   (default 1)
    """

    def __init__(
        self,
        high_score_threshold: float,
        low_score_threshold:  float,
        min_high_conf_count:  int,
      ):
        self.high_score_threshold = high_score_threshold
        self.low_score_threshold  = low_score_threshold
        self.min_high_conf_count  = min_high_conf_count

        from app.core.prompt_loader import prompt_loader
        self.warning = prompt_loader.get("kb.confidence_warning")

    async def run(self, state: PipelineState) -> PipelineState:
        """
        Annotate each chunk's metadata with confidence_level (and
        confidence_warning when low).  Returns chunks unchanged in order.
        """
        level, warning = self._assess(state.chunks)

        for rc in state.chunks:
            rc.metadata["confidence_level"] = level
            if warning:
                rc.metadata["confidence_warning"] = warning

        top_score_str   = f"{state.chunks[0].final_score:.4f}" if state.chunks else "N/A"
        high_conf_count = sum(1 for rc in state.chunks if rc.final_score >= self.high_score_threshold)
        logger.info(
            f"[ConfidenceStage] level={level}  "
            f"top_score={top_score_str}  "
            f"high_conf_count={high_conf_count}"
        )
        state.confidence = RetrievalConfidence(level=level, warning=warning, chunks=state.chunks)
        return state

    def _assess(self, chunks: List[RetrievedChunk]):
        """Core assessment logic, shared by run() and assess()."""
        if not chunks:
            return "empty", None

        top_score       = chunks[0].final_score
        high_conf_count = sum(
            1 for rc in chunks if rc.final_score >= self.high_score_threshold
        )

        if (top_score < self.low_score_threshold
                or high_conf_count < self.min_high_conf_count):
            return "low", self.warning

        return "high", None

# ═══════════════════════════════════════════════════════════════════════════
# PipelineConfig — clean typed bridge between ORM and Pipeline
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class PipelineConfig:
    """
    Flat, typed snapshot of all parameters needed to run the pipeline.
    Decouples RetrievalPipeline from the SQLAlchemy ORM model and makes
    the active configuration fully inspectable without a DB session.
    """
    kb_id:                 int
    final_top_k:           int

    # Source
    enable_query_rewrite:  bool
    enable_query_expansion: bool
    enable_query_hyde:     bool
    enable_vector:         bool
    enable_bm25:           bool
    vector_top_k:          int
    vector_score_threshold: float
    bm25_top_k:            int
    bm25_score_threshold:  float
    # Fusion
    fusion_mode:           FusionMode
    rrf_k:                 int
    vector_weight:         float
    rrf_top_k:             int
    # Post-processing
    enable_small_to_big:   bool
    # Reranking
    enable_reranker:       bool
    ranking_mode:          KBRankingMode
    rerank_top_k:          int
    # Metadata
    config_id:             Optional[str] = None
    # Confidence
    require_citation:                 bool  = True
    confidence_high_score_threshold:  float = 0.7
    confidence_low_score_threshold:   float = 0.5
    confidence_min_high_conf_count:   int   = 1
    query_expansion_num:   int = 3
    max_transform_queries: int = 5

    @classmethod
    def create(cls, 
        config              : StrategyConfig,                  
        ) -> "PipelineConfig":
        """
        Build a PipelineConfig object.
        """       
        
        try:
            fusion_mode = FusionMode(getattr(config, "rrf_mode", FusionMode.RRF.value))
        except ValueError:
            logger.warning(f"Unknown rrf_mode={config.rrf_mode!r}, using 'rrf'.")
            fusion_mode = FusionMode.RRF

        try:
            ranking_mode = KBRankingMode(
                getattr(config, "reranking_mode", KBRankingMode.HYBRID.value)
            )
        except ValueError:
            logger.warning(
                f"Unknown reranking_mode={config.reranking_mode!r}, using 'hybrid'."
            )
            ranking_mode = KBRankingMode.HYBRID

        return cls(
            kb_id                  = config.kb_id,
            final_top_k            = config.final_top_k,
            enable_query_rewrite   = getattr(config, "enable_query_rewrite", True),
            enable_query_expansion = getattr(config, "enable_query_expansion", True),
            enable_query_hyde      = getattr(config, "enable_query_hyde", True),
            enable_vector          = getattr(config, "enable_vector", True),
            enable_bm25            = config.enable_bm25,
            vector_top_k           = config.vector_top_k,
            vector_score_threshold = config.vector_score_threshold,
            bm25_top_k             = config.bm25_top_k,
            bm25_score_threshold   = config.bm25_score_threshold,
            fusion_mode            = fusion_mode,
            rrf_k                  = config.rrf_k,
            vector_weight          = config.vector_weight,
            rrf_top_k              = config.rrf_top_k,
            enable_small_to_big    = config.enable_small_to_big,
            enable_reranker        = config.enable_reranker,
            ranking_mode           = ranking_mode,
            rerank_top_k           = config.rerank_top_k,
            config_id              = config.config_id,
            require_citation                 = getattr(config, "require_citation", True),
            confidence_high_score_threshold  = getattr(config, "confidence_high_score_threshold", 0.7),
            confidence_low_score_threshold   = getattr(config, "confidence_low_score_threshold", 0.5),
            confidence_min_high_conf_count   = getattr(config, "confidence_min_high_conf_count", 1),
            query_expansion_num    = config.query_expansion_num,
            max_transform_queries  = config.max_transform_queries,            
        )


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline
# ═══════════════════════════════════════════════════════════════════════════

class RetrievalPipeline:
    """
    Assembles and executes a retrieval pipeline from a PipelineConfig.
    """

    def __init__(
        self,
        cfg:    PipelineConfig,
        stages: List[BaseStage],
        cache:  Optional[BaseStore] = None,
    ):
        self.cfg    = cfg
        self.stages = stages
        self._cache = cache
        if cache is not None:
            logger.info(
                f"[Pipeline] kb={cfg.kb_id} cache enabled "
                f"(backend={type(cache).__name__})"
            )

    # ── factory ──────────────────────────────────────────────────────────

    @classmethod
    async def create(
        cls,
        config:          StrategyConfig,
        llm_config:      LLM,
        container       ,         
        cache_backend:   Optional[BaseStore]   = None,
        cache_max_size:  int                   = 512,        
    ) -> RetrievalPipeline:
        """
        Build a fully-configured RetrievalPipeline from a StrategyConfig row.
        """

        from app.core.service_container import ServiceContainer
        if not isinstance(container, ServiceContainer):
            raise TypeError(f"Expected ServiceContainer, got {type(container)}")           

        cfg  = PipelineConfig.create(
            config=config,             
        )        
        
        kb_id = cfg.kb_id
        stages: List[BaseStage] = []

        from app.core.prompt_loader import prompt_loader

        llm_client = LLMClient(
            base_url=llm_config.base_url,
            api_key=llm_config.api_key,
            temperature=llm_config.temperature,
        )

        # Query stages
        query_transforms: List[BaseQueryStage] = []
        if cfg.enable_query_rewrite:
            prompt_template = prompt_loader.get("kb.query_rewrite")
            query_transforms.append(
                QueryRewriteStage(
                    llm_client    = llm_client,
                    model         = llm_config.model_name,
                    prompt_template = prompt_template,
                )
            )
        if cfg.enable_query_expansion:
            prompt_template = prompt_loader.get("kb.query_expansion")
            query_transforms.append(
                QueryExpansionStage(
                    llm_client    = llm_client,
                    model         = llm_config.model_name,
                    prompt_template = prompt_template,
                    expansion_num = cfg.query_expansion_num,
                )
            )
        if cfg.enable_query_hyde:
            prompt_template = prompt_loader.get("kb.hyde")
            query_transforms.append(
                HyDEStage(
                    llm           = llm_client,
                    model         = llm_config.model_name,
                    prompt_template = prompt_template,
                )
            )
        if query_transforms:
            stages.append(
                QueryTransformStage(
                    query_transforms = query_transforms,
                    max_queries      = cfg.max_transform_queries,
                )
            )

        # Source stages
        vector_stage = None
        BM25_stage   = None
        if cfg.enable_vector:
            vs_manager = await container.vector_registry.get(kb_id)
            vector_stage = VectorStage(
                vs_manager      = vs_manager,
                kb_id           = kb_id,
                default_top_k           = cfg.vector_top_k,
                score_threshold = cfg.vector_score_threshold,                
            )
        if cfg.enable_bm25:
            from app.infra.search.bm25_manager import bm25_manager
            BM25_stage = BM25Stage(
                bm25_manager    = bm25_manager,
                kb_id           = kb_id,
                default_top_k           = cfg.bm25_top_k,
                score_threshold = cfg.bm25_score_threshold,
            )
        if not vector_stage and not BM25_stage:
            raise ValueError(
                f"StrategyConfig {cfg.config_id}: "
                "at least one of enable_vector / enable_bm25 must be True."
            )

        # Adaptive TopK
        stages.append(
            AdaptiveTopKStage(                
                base_vector_topk = cfg.vector_top_k,
                base_bm25_topk   = cfg.bm25_top_k,
            )
        )

        stages.append(RetrievalStage(vector_stage=vector_stage, bm25_stage=BM25_stage))
        stages.append(FusionStage(
            mode          = cfg.fusion_mode,
            rrf_k         = cfg.rrf_k,
            vector_weight = cfg.vector_weight,
            rrf_top_k     = cfg.rrf_top_k,
        ))

        # Post stages (before rerank)
        if cfg.enable_small_to_big:
            stages.append(SmallToBigStage(pc_db=container.pc_db, kb_id=kb_id))

        stages.append(TextHydrationStage(chunk_db=container.chunk_db))

        extra = config.extra_config or {}
        reranker_config = extra.get("reranker")

        # Rerank stage
        if cfg.enable_reranker:            
            try:
                mode = RerankMode.SCORE
                if cfg.ranking_mode == KBRankingMode.LLM:
                    mode = RerankMode.LLM
                elif cfg.ranking_mode == KBRankingMode.RERANK:
                    mode = RerankMode.BGE
                reranker = RerankerFactory.create(
                    mode=mode,                    
                    top_k=cfg.rerank_top_k,
                    reranker_config=reranker_config,
                    llm_config=llm_config
                )
                logger.info(
                    f"[Pipeline] reranker auto-built  "
                    f"backend={reranker_config.get('backend')}  "
                    f"kb={cfg.kb_id}"
                )
                rerank_stage = RerankStage(
                    mode     = cfg.ranking_mode,                    
                    reranker = reranker,
                )
                stages.append(rerank_stage)
            except Exception as exc:
                # Build failures do not halt the pipeline; RerankStage will automatically downgrade to hybrid.
                logger.warning(
                    f"[Pipeline] reranker build failed: {exc}  "
                    f"— RerankStage will degrade to hybrid"
                )

        stages.append(
            AdaptiveThresholdStage(
                std_factor=0.5,
                min_keep=cfg.final_top_k
            )
        )

        stages.append(ContextTrimStage(max_chunks=cfg.final_top_k))

        # Citation stage
        if cfg.require_citation:
            domain = await container.domain_db.get_domain_by_kb_id(kb_id)       
            plugin = container.domain_registry.get(domain.name)
            stages.append(CitationStage(doc_db=container.doc_db,
                merger=plugin.citation_merger or CitationMerger()))

        # Confidence stage
        confidence_stage = ConfidenceStage(
            high_score_threshold = cfg.confidence_high_score_threshold,
            low_score_threshold  = cfg.confidence_low_score_threshold,
            min_high_conf_count  = cfg.confidence_min_high_conf_count
        )
        stages.append(confidence_stage)

        # Cache
        cache: Optional[BaseStore] = None
        if cache_backend is not None:
            cache = cache_backend
        else:
            cache = create_cache_backend(
                namespace="retrieval", backend_type="memory", max_size=cache_max_size
            )

        return cls(
            cfg    = cfg,
            stages = stages,
            cache  = cache,
        )

    # ── run ───────────────────────────────────────────────────────────────

    async def run(
        self,
        query:           str,
        metadata_filter: Optional[dict] = None,
    ) -> PipelineState:
        """
        Execute the full retrieval pipeline for a query.

        Returns up to cfg.final_top_k RetrievedChunk objects sorted by
        final_score descending.

        Cache behaviour
        ---------------
        The complete RetrievalConfidence result is cached keyed by
        (kb_id, config_id, query, metadata_filter).  Cache is skipped when
        metadata_filter is dynamic (changes per request), but still works
        correctly because it is part of the key.
        """
        state = PipelineState(
            original_query=query,
            metadata_filter=metadata_filter,
        )
        if not query or not query.strip():
            state.confidence = RetrievalConfidence(level="empty", warning="", chunks=[])
            return state

        # ── cache read ────────────────────────────────────────────────────
        cache_key = self._make_cache_key(query, metadata_filter)
        if self._cache is not None:
            cached = self._cache.mget([cache_key])[0]
            if cached is not None:
                logger.debug(
                    f"[Pipeline] cache hit  kb={self.cfg.kb_id}  "
                    f"key={cache_key[:12]}…  query={query[:60]!r}"
                )
                state.confidence = RetrievalConfidence.from_bytes(cached)
                return state
            logger.debug(
                f"[Pipeline] cache miss kb={self.cfg.kb_id}  "
                f"key={cache_key[:12]}…"
            )

        logger.info(
            f"[Pipeline] kb={self.cfg.kb_id}  config={self.cfg.config_id}  "
            f"ranking={self.cfg.ranking_mode.value}  "
            f"query={query[:60]!r}"
        )

        for stage in self.stages:
            state = await stage.run(state)

        # ── cache write ───────────────────────────────────────────────────
        if self._cache is not None and state.confidence is not None:
            self._cache.mset([(cache_key, state.confidence.to_bytes())])
            logger.debug(
                f"[Pipeline] cached     kb={self.cfg.kb_id}  key={cache_key[:12]}…"
            )

        return state

    def _make_cache_key(
        self,
        query:           str,
        metadata_filter: Optional[dict] = None,
    ) -> str:
        """
        Build a deterministic cache key scoped to this KB and config version.

        Including kb_id and config_id ensures that keys never collide across
        knowledge bases or after a strategy config version bump.
        """
        payload = json.dumps(
            {
                "kb_id":     self.cfg.kb_id,
                "config_id": self.cfg.config_id,
                "query":     query,
                "filter":    metadata_filter,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get_cache_stats(self) -> Optional[dict]:
        """Return cache hit/miss statistics, or None if cache is disabled."""
        if self._cache is None:
            return None
        if hasattr(self._cache, "get_stats"):
            return self._cache.get_stats()
        return {"info": "Cache backend does not expose stats."}

    def clear_cache(self) -> None:
        """Manually evict all cached retrieval results for this pipeline."""
        if self._cache is not None and hasattr(self._cache, "clear"):
            self._cache.clear()
            logger.info(f"[Pipeline] cache cleared  kb={self.cfg.kb_id}")

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def to_langchain_documents(result: RetrievalConfidence) -> List[Document]:
        """Convert pipeline output to standard LangChain Document objects."""
        return [rc.to_langchain_document() for rc in result.chunks]

    def as_retriever(self) -> "PipelineRetriever":
        """
        Return a LangChain BaseRetriever wrapping this pipeline.
        """
        return PipelineRetriever(pipeline=self)


# ═══════════════════════════════════════════════════════════════════════════
# LangChain Retriever adapter
# ═══════════════════════════════════════════════════════════════════════════

class PipelineRetriever(BaseRetriever):
    """LangChain BaseRetriever backed by a RetrievalPipeline."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    pipeline: RetrievalPipeline = Field(..., exclude=True)

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        #This approach is valid in synchronous environments (pure scripts/testing), but should not be used in production.
        raise NotImplementedError(
            "PipelineRetriever only supports async; use ainvoke() or aget_relevant_documents()."
        )

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: ...
    ) -> List[Document]:
        result = await self.pipeline.run(query)
        return RetrievalPipeline.to_langchain_documents(result)


def deduplicate_chunks(chunks: List[RetrievedChunk]):
    seen = set()
    unique = []
    for c in chunks:
        if c.chunk_id not in seen:
            seen.add(c.chunk_id)
            unique.append(c)
    return unique

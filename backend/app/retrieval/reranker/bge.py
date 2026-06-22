#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-05
# @description: BGE reranker — unified implementation with pluggable scoring backends.
#
# Design
# ──────
# BGEReranker owns the pipeline: batching hand-off, path tagging, top-k
# truncation.  The *how-to-score* is delegated to a ScoringBackend:
#
#   ┌─────────────────────────────────────────────────────┐
#   │  BGEReranker.rerank(query, chunks, top_k)           │
#   │    └── backend.score(query, passages) → List[float] │
#   └─────────────────────────────────────────────────────┘
#            │                  │                 │
#   LocalScoringBackend  RemoteScoringBackend  OllamaEmbeddingBackend
#   (HuggingFace/torch)  (Jina/Cohere/xInf…)  (cosine via embed API)
#
# Supported backends
# ──────────────────
# LocalScoringBackend    — loads BAAI/bge-reranker-* locally via HuggingFace.
#                          Requires: pip install transformers torch
#
# RemoteScoringBackend   — POST {"query", "documents"} to any OpenAI-compatible
#                          /rerank endpoint (Jina, Cohere, xinference, infinity…).
#                          Uses LLMClient for auth headers.
#                          Requires: pip install httpx
#
# OllamaEmbeddingBackend — calls LLMClient.embed() → cosine similarity.
#                          Not a true cross-encoder, but zero extra deps.
#
# Usage
# ─────
#   # Local HuggingFace (most accurate)
#   reranker = BGEReranker.local()
#   reranker = BGEReranker.local(model_name="BAAI/bge-reranker-large", device="cuda")
#
#   # Remote API  (Jina / Cohere / xinference / infinity)
#   reranker = BGEReranker.remote(
#       client = LLMClient(base_url="https://api.jina.ai/v1", api_key="jina_..."),
#       model  = "jina-reranker-v2-base-multilingual",
#   )
#
#   # Ollama embedding similarity  (no torch needed)
#   reranker = BGEReranker.ollama(
#       client = LLMClient(base_url="http://localhost:11434/v1", api_key="none"),
#       model  = "bge-large-zh",
#   )
#
#   # All three are drop-in for BaseReranker:
#   pipeline = RetrievalPipeline.from_config(config, vs, bm25, pc_db, reranker=reranker)

from __future__ import annotations

import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import asyncio
import math
from abc import ABC, abstractmethod
from typing import List, Optional

from loguru import logger

from app.retrieval.reranker.base import BaseReranker, Scorable
from app.infra.llm import LLMClient

# ═══════════════════════════════════════════════════════════════════════════
# ScoringBackend interface
# ═══════════════════════════════════════════════════════════════════════════

class ScoringBackend(ABC):
    """
    Pluggable scoring backend for BGEReranker.

    Receives a query and a list of passage strings; returns a float score
    in [0, 1] for each passage, in the same order as the input.
    """

    @abstractmethod
    async def score(self, query: str, passages: List[str]) -> List[float]:
        """
        Score each (query, passage) pair.

        Args
        ────
        query       The search query.
        passages    Passage texts to score, in original order.

        Returns
        ───────
        List[float] of length == len(passages), values in [0, 1].
        Higher means more relevant.
        """

# ═══════════════════════════════════════════════════════════════════════════
# Backend 1 — Local HuggingFace cross-encoder
# ═══════════════════════════════════════════════════════════════════════════

class LocalScoringBackend(ScoringBackend):
    """
    Scores (query, passage) pairs using a locally-loaded BGE cross-encoder.

    The model is loaded once at construction and kept in memory.
    Forward passes run inside asyncio.to_thread to avoid blocking the loop.

    Args
    ────
    model_name  HuggingFace model id (default "BAAI/bge-reranker-base").
    device      "cuda" | "cpu" | None (auto-detect).
    max_length  Max tokens per pair; longer pairs are truncated.
    batch_size  Pairs per forward pass; reduce on OOM.
    cache_dir   Local directory for HuggingFace model cache.
    """

    def __init__(
        self,
        model_name: str           = "BAAI/bge-reranker-base",
        device:     Optional[str] = None,
        max_length: int           = 512,
        batch_size: int           = 64,
        cache_dir:  Optional[str] = None,
    ):
        try:
            import torch
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )
        except ImportError as e:
            raise ImportError(
                "LocalScoringBackend requires 'transformers' and 'torch'.\n"
                "Install with:  pip install transformers torch"
            ) from e

        self._torch     = torch
        self.model_name = model_name
        self.max_length = max_length
        self.batch_size = batch_size

        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device

        logger.info(f"[LocalScoringBackend] Loading {model_name} on {device} …")

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir=cache_dir,
        )
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            cache_dir=cache_dir,
        )
        self.model.eval()
        self.model.to(self.device)
        logger.info("[LocalScoringBackend] Model ready.")

    async def score(self, query: str, passages: List[str]) -> List[float]:
        return await asyncio.to_thread(self._score_sync, query, passages)

    def _score_sync(self, query: str, passages: List[str]) -> List[float]:
        torch       = self._torch
        all_scores: List[float] = []

        for start in range(0, len(passages), self.batch_size):
            batch = passages[start: start + self.batch_size]
            pairs = [[query, p] for p in batch]

            encoded = self.tokenizer(
                pairs,
                padding        = True,
                truncation     = True,
                max_length     = self.max_length,
                return_tensors = "pt",
            ).to(self.device)

            with torch.no_grad():
                logits = self.model(**encoded).logits.squeeze(-1)

            scores = torch.sigmoid(logits).cpu().float().tolist()
            if isinstance(scores, float):
                scores = [scores]
            all_scores.extend(scores)

        return all_scores


# ═══════════════════════════════════════════════════════════════════════════
# Backend 2 — Remote reranking API
# ═══════════════════════════════════════════════════════════════════════════

class RemoteScoringBackend(ScoringBackend):
    """
    Scores passages by calling an external OpenAI-compatible reranking API.

    Compatible services
    ───────────────────
    Jina AI     base_url = "https://api.jina.ai/v1"
                model    = "jina-reranker-v2-base-multilingual"

    Cohere      base_url = "https://api.cohere.com/v1"
                model    = "rerank-multilingual-v3.0"

    xinference  base_url = "http://localhost:9997/v1"
                model    = <your deployed model>

    infinity    base_url = "http://localhost:7997"
                model    = "BAAI/bge-reranker-v2-m3"

    Request sent
    ────────────
    POST <base_url>/rerank
    {
        "model":     "<model>",
        "query":     "<query>",
        "documents": ["passage 0", "passage 1", ...],
        "top_n":     <len(passages)>
    }

    Expected response
    ─────────────────
    {
        "results": [
            {"index": 0, "relevance_score": 0.92},
            {"index": 2, "relevance_score": 0.71},
            ...
        ]
    }

    Args
    ────
    client      LLMClient — used for its base_url and api_key.
    model       Model name forwarded in the request body.
    batch_size  Max documents per request (some providers cap this).
    timeout     HTTP timeout in seconds.
    """

    def __init__(
        self,
        client:     LLMClient,
        model:      str,
        batch_size: int   = 100,
        timeout:    float = 30.0,
    ):
        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "RemoteScoringBackend requires 'httpx'.\n"
                "Install with:  pip install httpx"
            ) from e

        self._httpx     = httpx
        self.model      = model
        self.batch_size = batch_size
        self.timeout    = timeout

        # Build rerank URL: strip trailing /v1 then re-append /v1/rerank
        base = client.base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        self.rerank_url = base.rstrip("/") + "/v1/rerank"

        self.headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {client.api_key or 'none'}",
        }
        logger.info(
            f"[RemoteScoringBackend] endpoint={self.rerank_url}  model={model}"
        )

    async def score(self, query: str, passages: List[str]) -> List[float]:
        scores  = [0.0] * len(passages)
        batches = [
            (start, passages[start: start + self.batch_size])
            for start in range(0, len(passages), self.batch_size)
        ]
        results = await asyncio.gather(
            *[self._call_api(query, texts) for _, texts in batches]
        )
        for (start, texts), batch_scores in zip(batches, results):
            for i, s in enumerate(batch_scores):
                scores[start + i] = s
        return scores

    async def _call_api(self, query: str, passages: List[str]) -> List[float]:
        payload = {
            "model":     self.model,
            "query":     query,
            "documents": passages,
            "top_n":     len(passages),
        }
        try:
            async with self._httpx.AsyncClient(timeout=self.timeout) as http:
                resp = await http.post(
                    self.rerank_url, json=payload, headers=self.headers
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error(f"[RemoteScoringBackend] API call failed: {exc}")
            return [0.0] * len(passages)

        index_to_score: dict[int, float] = {
            item["index"]: float(item["relevance_score"])
            for item in data.get("results", [])
        }
        return [index_to_score.get(i, 0.0) for i in range(len(passages))]


# ═══════════════════════════════════════════════════════════════════════════
# Backend 3 — Ollama embedding cosine similarity
# ═══════════════════════════════════════════════════════════════════════════

class OllamaEmbeddingBackend(ScoringBackend):
    """
    Scores passages by cosine similarity between query and passage embeddings.

    Uses LLMClient.embed() — no torch or extra dependencies required.
    Not a true cross-encoder; accuracy is between raw vector scores and
    a full cross-encoder reranker.

    Setup
    ─────
    ollama pull bge-large-zh       # Chinese + English, 1.5 GB
    ollama pull nomic-embed-text   # English only, 274 MB
    ollama pull mxbai-embed-large  # English, high quality, 669 MB

    Args
    ────
    client          LLMClient(base_url="http://localhost:11434/v1", api_key="none")
    model           Ollama embedding model name.
    query_prefix    Prepended to query before embedding.  Auto-set to the BGE
                    asymmetric instruction when model name contains "bge".
    passage_prefix  Prepended to each passage (usually empty).
    batch_size      Passages per /embeddings request.
    """

    _BGE_QUERY_PREFIX = (
        "Represent this sentence for searching relevant passages: "
    )

    def __init__(
        self,
        client:         LLMClient,
        model:          str   = "bge-large-zh",
        query_prefix:   str   = "",
        passage_prefix: str   = "",
        batch_size:     int   = 64,
    ):
        self.client         = client
        self.model          = model
        self.passage_prefix = passage_prefix
        self.batch_size     = batch_size

        if not query_prefix and "bge" in model.lower():
            query_prefix = self._BGE_QUERY_PREFIX
            logger.debug(
                "[OllamaEmbeddingBackend] BGE model — applying query prefix."
            )
        self.query_prefix = query_prefix

    async def score(self, query: str, passages: List[str]) -> List[float]:
        query_vec, passage_vecs = await asyncio.gather(
            self._embed_one(self.query_prefix + query.strip()),
            self._embed_many([self.passage_prefix + p for p in passages]),
        )
        return [_cosine(query_vec, p_vec) for p_vec in passage_vecs]

    async def _embed_one(self, text: str) -> List[float]:
        vecs = await asyncio.to_thread(self.client.embed, self.model, [text])
        return vecs[0]

    async def _embed_many(self, texts: List[str]) -> List[List[float]]:
        from app.infra.llm import LLMClientError
        all_vecs: List[List[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start: start + self.batch_size]
            try:
                vecs = await asyncio.to_thread(self.client.embed, self.model, batch)
                all_vecs.extend(vecs)
            except LLMClientError as exc:
                logger.error(f"[OllamaEmbeddingBackend] embed batch failed: {exc}")
                all_vecs.extend([[0.0]] * len(batch))
        return all_vecs


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    return 0.0 if (na == 0.0 or nb == 0.0) else dot / (na * nb)


# ═══════════════════════════════════════════════════════════════════════════
# BGEReranker — pipeline orchestrator
# ═══════════════════════════════════════════════════════════════════════════

class BGEReranker(BaseReranker):
    """
    BGE reranker with pluggable scoring backends.

    Owns the shared pipeline: score collection, path tagging, sorting,
    and top-k truncation.  Delegates actual scoring to a ScoringBackend.

    Use the factory classmethods rather than constructing directly:

        BGEReranker.local()   — HuggingFace cross-encoder (most accurate)
        BGEReranker.remote()  — External REST reranking API
        BGEReranker.ollama()  — Ollama embedding cosine (no torch needed)

    Custom backend:

        reranker = BGEReranker(backend=MyBackend())
    """

    def __init__(self, backend: ScoringBackend):
        self.backend = backend

    # ── factory methods ───────────────────────────────────────────────────

    @classmethod
    def local(
        cls,
        model_name: str           = "BAAI/bge-reranker-base",
        device:     Optional[str] = None,
        max_length: int           = 512,
        batch_size: int           = 64,
        cache_dir:  Optional[str] = None,
    ) -> BGEReranker:
        """
        Load a BGE cross-encoder locally via HuggingFace Transformers.

        Requires: pip install transformers torch

        model_name choices
        ──────────────────
        "BAAI/bge-reranker-base"   fast, Chinese+English        (default)
        "BAAI/bge-reranker-large"  higher accuracy
        "BAAI/bge-reranker-v2-m3"  multilingual, best quality
        """
        return cls(LocalScoringBackend(
            model_name = model_name,
            device     = device,
            max_length = max_length,
            batch_size = batch_size,
            cache_dir  = cache_dir,
        ))

    @classmethod
    def remote(
        cls,
        client:     LLMClient,
        model:      str,
        batch_size: int   = 100,
        timeout:    float = 30.0,
    ) -> BGEReranker:
        """
        Call an external OpenAI-compatible reranking API.

        Requires: pip install httpx

        Example providers
        ─────────────────
        Jina AI:
            BGEReranker.remote(
                client = LLMClient("https://api.jina.ai/v1", api_key="jina_..."),
                model  = "jina-reranker-v2-base-multilingual",
            )

        Cohere:
            BGEReranker.remote(
                client = LLMClient("https://api.cohere.com/v1", api_key="co_..."),
                model  = "rerank-multilingual-v3.0",
            )

        Self-hosted xinference (BGE model deployed locally):
            BGEReranker.remote(
                client = LLMClient("http://localhost:9997/v1", api_key="none"),
                model  = "bge-reranker-v2-m3",
            )

        Self-hosted infinity:
            BGEReranker.remote(
                client = LLMClient("http://localhost:7997", api_key="none"),
                model  = "BAAI/bge-reranker-v2-m3",
            )
        """
        return cls(RemoteScoringBackend(
            client     = client,
            model      = model,
            batch_size = batch_size,
            timeout    = timeout,
        ))

    @classmethod
    def ollama(
        cls,
        client:         LLMClient,
        model:          str   = "bge-large-zh",
        query_prefix:   str   = "",
        passage_prefix: str   = "",
        batch_size:     int   = 64,
    ) -> BGEReranker:
        """
        Re-score via Ollama embedding cosine similarity.

        No torch required — uses only LLMClient.embed().
        Accuracy is below a true cross-encoder but above raw vector scores.

        Pull the embedding model first:
            ollama pull bge-large-zh       # Chinese + English (recommended)
            ollama pull nomic-embed-text   # English only, fast
            ollama pull mxbai-embed-large  # English, high quality

        Example:
            BGEReranker.ollama(
                client = LLMClient("http://localhost:11434/v1", api_key="none"),
                model  = "bge-large-zh",
            )
        """
        return cls(OllamaEmbeddingBackend(
            client         = client,
            model          = model,
            query_prefix   = query_prefix,
            passage_prefix = passage_prefix,
            batch_size     = batch_size,
        ))

    # ── pipeline ──────────────────────────────────────────────────────────

    async def rerank(
        self,
        query:  str,
        chunks: List[Scorable],
        top_k:  int,
    ) -> List[Scorable]:
        """
        Score all chunks via the configured backend, update scores,
        and return the top_k results sorted by final_score descending.
        """
        if not chunks:
            return chunks

        scores = await self.backend.score(query, [rc.text for rc in chunks])

        for rc, score in zip(chunks, scores):
            rc.rerank_score = score
            rc.final_score  = score
            if "rerank" not in rc.retrieval_path:
                rc.retrieval_path.append("rerank")

        chunks.sort(key=lambda rc: rc.final_score, reverse=True)
        result = chunks[:top_k]

        logger.debug(
            f"[BGEReranker] backend={type(self.backend).__name__}  "
            f"in={len(chunks)}  out={len(result)}  "
            f"top_score={result[0].final_score:.4f}"
        )
        return result

    # ── convenience ───────────────────────────────────────────────────────

    async def score_pairs(
        self, query: str, passages: List[str]
    ) -> List[float]:
        """
        Score raw (query, passage) pairs without Scorable wrappers.
        Useful for evaluation, offline batch scoring, or unit tests.
        """
        return await self.backend.score(query, passages)
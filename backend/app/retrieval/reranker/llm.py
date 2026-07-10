#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-05
# @description: LLM-based reranker — concrete implementation of BaseLLMReranker.
#
# Two implementations are provided:
#
#   LLMReranker         — calls score_one() for every chunk in parallel.
#                         Simple, accurate, but costs N LLM calls per query.
#
#   LLMBatchReranker    — sends ALL chunks in a single LLM call and parses a
#                         JSON ranking list back. Faster and cheaper; trades
#                         some accuracy for throughput.
#
# Both are drop-in for RerankStage(mode=RankingMode.LLM, reranker=...).
#
# Usage
# -----
#   from client import LLMClient
#   from llm_reranker import LLMReranker, LLMBatchReranker
#
#   llm = LLMClient(base_url="...", api_key="...")
#
#   # Option A — one call per chunk (more accurate)
#   reranker = LLMReranker(client=llm, model="qwen-plus")
#
#   # Option B — one call for all chunks (faster)
#   reranker = LLMBatchReranker(client=llm, model="qwen-plus", batch_size=20)
#
#   pipeline = RetrievalPipeline.from_config(config, vs, bm25, pc_db, reranker=reranker)

from __future__ import annotations

import asyncio
import json
import re
from typing import List, Optional

from loguru import logger

from app.retrieval.reranker.base import BaseLLMReranker, Scorable
from app.runtime.llm.models import LLMClientError
from app.runtime.llm.client import LLMClient

# ═══════════════════════════════════════════════════════════════════════════
# Shared prompt templates
# ═══════════════════════════════════════════════════════════════════════════

_SCORE_ONE_SYSTEM = """\
You are a relevance scoring assistant.
Given a user query and a text passage, output a single decimal number between \
0.00 and 1.00 representing how relevant the passage is to the query.
Rules:
- Output ONLY the number, nothing else.
- 1.00 = perfectly relevant.  0.00 = completely irrelevant.
- Use at most 2 decimal places.\
"""

_SCORE_ONE_USER = """\
Query: {query}

Passage:
{text}

Relevance score:\
"""

_BATCH_SYSTEM = """\
You are a relevance ranking assistant.
You will receive a user query and a numbered list of text passages.
Return a JSON array of objects, one per passage, sorted from most relevant \
to least relevant.

Each object must have exactly two keys:
  "index" : the original 0-based integer index of the passage
  "score" : a relevance score between 0.00 and 1.00 (2 decimal places)

Output ONLY the JSON array, no explanation, no markdown fences.\
"""

_BATCH_USER = """\
Query: {query}

Passages:
{passages}

Return the ranked JSON array:\
"""


# ═══════════════════════════════════════════════════════════════════════════
# Option A — one LLM call per chunk  (parallel)
# ═══════════════════════════════════════════════════════════════════════════

class LLMReranker(BaseLLMReranker):
    """
    Reranker that scores each chunk independently via one LLM call.

    Parallelism is handled by BaseLLMReranker.rerank() using asyncio.gather,
    so all N calls are issued concurrently and complete in roughly one RTT.

    Args
    ----
    client          LLMClient instance (shared with the rest of the system).
    model           Model name to use for scoring.
    max_concurrency Max simultaneous LLM calls (throttles asyncio.gather).
                    Set to None to use no limit (default).
    fallback_score  Score assigned when the LLM returns an unparseable response.
    """

    def __init__(
        self,
        client:          LLMClient,
        model:           str,
        max_concurrency: Optional[int] = 2,
        fallback_score:  float         = 0.0,
    ):
        self.client          = client
        self.model           = model
        self.fallback_score  = fallback_score
        self._semaphore      = (
            asyncio.Semaphore(max_concurrency)
            if max_concurrency is not None
            else None
        )

    async def score_one(self, query: str, text: str) -> float:
        """
        Ask the LLM to score a single (query, passage) pair.
        Returns a float in [0, 1].  Falls back to self.fallback_score on error.
        """
        messages = [
            {"role": "system", "content": _SCORE_ONE_SYSTEM},
            {
                "role": "user",
                "content": _SCORE_ONE_USER.format(
                    query=query.strip(),
                    text=text.strip(),
                ),
            },
        ]

        async def _call() -> float:
            try:
                response = await asyncio.to_thread(
                    self.client.chat,
                    model     = self.model,
                    messages  = messages,
                    stream    = False,
                    max_tokens = 8,          # score is always ≤ 4 chars
                    temperature = 0.0,       # deterministic scoring
                )
                raw = str(response).strip()
                return _parse_score(raw, self.fallback_score)
            except LLMClientError as exc:
                logger.warning(f"[LLMReranker] score_one failed: {exc}")
                return self.fallback_score

        if self._semaphore is not None:
            async with self._semaphore:
                return await _call()
        return await _call()


# ═══════════════════════════════════════════════════════════════════════════
# Option B — one LLM call for all chunks  (batch)
# ═══════════════════════════════════════════════════════════════════════════

class LLMBatchReranker(BaseLLMReranker):
    """
    Reranker that scores and ranks all chunks in a single LLM call.

    Sends the query + all passages together and asks the model to return a
    JSON ranking.  Much cheaper than LLMReranker for large candidate sets,
    but accuracy depends on the model's ability to reason over long context.

    For very large candidate sets (> batch_size chunks), the list is split
    into batches and results are merged by score descending.

    Args
    ----
    client          LLMClient instance.
    model           Model name to use for ranking.
    batch_size      Max passages per LLM call (default 20).
    fallback_score  Score used when a passage is missing from the LLM response.
    max_passage_len Truncate each passage to this many characters before sending
                    to the LLM, to avoid exceeding context limits.
    """

    def __init__(
        self,
        client:           LLMClient,
        model:            str,
        batch_size:       int   = 20,
        fallback_score:   float = 0.0,
        max_passage_len:  int   = 512,
    ):
        self.client          = client
        self.model           = model
        self.batch_size      = batch_size
        self.fallback_score  = fallback_score
        self.max_passage_len = max_passage_len

    # BaseLLMReranker requires score_one; we provide a stub because this class
    # overrides rerank() directly and never calls score_one per-chunk.
    async def score_one(self, query: str, text: str) -> float:  # pragma: no cover
        raise NotImplementedError(
            "LLMBatchReranker uses batch reranking; score_one is not called directly."
        )

    async def rerank(
        self,
        query:  str,
        chunks: List[Scorable],
        top_k:  int,
    ) -> List[Scorable]:
        """
        Score all chunks in batches of self.batch_size, merge, and return top_k.
        """
        if not chunks:
            return chunks

        # Split into batches
        batches = [
            chunks[i: i + self.batch_size]
            for i in range(0, len(chunks), self.batch_size)
        ]

        # Score all batches concurrently
        batch_results: List[List[Scorable]] = await asyncio.gather(
            *[self._score_batch(query, batch) for batch in batches]
        )

        # Flatten and sort globally
        all_chunks: List[Scorable] = [
            rc for batch in batch_results for rc in batch
        ]
        all_chunks.sort(key=lambda rc: rc.final_score, reverse=True)

        result = all_chunks[:top_k]
        for rc in result:
            if "llm" not in rc.retrieval_path:
                rc.retrieval_path.append("llm")

        logger.debug(
            f"[LLMBatchReranker] in={len(chunks)}  batches={len(batches)}"
            f"  out={len(result)}"
        )
        return result

    async def _score_batch(
        self,
        query:  str,
        chunks: List[Scorable],
    ) -> List[Scorable]:
        """Score one batch and attach rerank_score / final_score to each chunk."""

        passages = "\n\n".join(
            f"[{i}] {rc.text[:self.max_passage_len]}"
            for i, rc in enumerate(chunks)
        )

        messages = [
            {"role": "system", "content": _BATCH_SYSTEM},
            {
                "role": "user",
                "content": _BATCH_USER.format(
                    query    = query.strip(),
                    passages = passages,
                ),
            },
        ]

        index_to_score: dict[int, float] = {}
        try:
            response = await asyncio.to_thread(
                self.client.chat,
                model       = self.model,
                messages    = messages,
                stream      = False,
                temperature = 0.0,
                max_tokens  = 512,
            )
            index_to_score = _parse_batch_response(str(response), self.fallback_score)
        except LLMClientError as exc:
            logger.warning(f"[LLMBatchReranker] _score_batch failed: {exc}")

        for i, rc in enumerate(chunks):
            score          = index_to_score.get(i, self.fallback_score)
            rc.rerank_score = score
            rc.final_score  = score

        return chunks


# ═══════════════════════════════════════════════════════════════════════════
# Parsing helpers
# ═══════════════════════════════════════════════════════════════════════════

def _parse_score(raw: str, fallback: float) -> float:
    """
    Parse a score string like "0.87" or "0.9" into a float clamped to [0, 1].
    Falls back to `fallback` if parsing fails.
    """
    try:
        match = re.search(r"\d+(?:\.\d+)?", raw)
        if not match:
            raise ValueError("no number found")
        score = float(match.group())
        return max(0.0, min(1.0, score))
    except (ValueError, TypeError) as exc:
        logger.warning(f"[LLMReranker] Could not parse score from {raw!r}: {exc}")
        return fallback


def _parse_batch_response(raw: str, fallback: float) -> dict[int, float]:
    """
    Parse a JSON array like:
        [{"index": 0, "score": 0.95}, {"index": 2, "score": 0.70}, ...]
    into a dict {index: score}.

    Strips markdown fences if the model wraps the JSON in them.
    Falls back to an empty dict (all chunks get fallback_score) on error.
    """
    try:
        # Strip optional ```json ... ``` fences
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        data    = json.loads(cleaned)

        result: dict[int, float] = {}
        for item in data:
            idx   = int(item["index"])
            score = max(0.0, min(1.0, float(item["score"])))
            result[idx] = score
        return result

    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.warning(f"[LLMBatchReranker] Could not parse batch response: {exc}\n{raw!r}")
        return {}

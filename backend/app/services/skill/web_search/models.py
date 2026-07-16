#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-01
# @description: WebSearch Models

from dataclasses import dataclass, field
from typing import List

from app.retrieval.reranker.base import Scorable


@dataclass
class WebSearchResult(Scorable):
    """
    A single search result flowing through the pipeline.

    Scorable protocol compatibility
    ────────────────────────────────
    This dataclass satisfies the Scorable structural protocol defined in
    reranker_base.py, so BGEReranker and LLMReranker / LLMBatchReranker can
    operate on WebSearchResult objects directly without any wrapper.

    Mapping:
      Scorable.text           ← effective_text()  (property)
      Scorable.final_score    ← final_score        (dataclass field)
      Scorable.rerank_score   ← rerank_score       (dataclass field)
      Scorable.retrieval_path ← pipeline_path      (same list, aliased by property)
    """
    title:        str
    url:          str
    snippet:      str              # DDG abstract (always present)
    content:      str   = ""       # full page text (filled by FetchStage)
    position:     int   = 0        # original DDG rank (1-based)
    final_score:  float = 0.0      # written by RerankStage
    rerank_score: float = 0.0      # raw model output (set by reranker)
    pipeline_path: List[str] = field(default_factory=list)

    # ── Scorable protocol ─────────────────────────────────────────────────

    @property
    def text(self) -> str:
        """Scorable.text — returns effective page content for scoring."""
        return self.effective_text()

    @property
    def retrieval_path(self) -> List[str]:
        """Scorable.retrieval_path — aliased to pipeline_path."""
        return self.pipeline_path

    @retrieval_path.setter
    def retrieval_path(self, value: List[str]) -> None:
        self.pipeline_path = value

    # ── helpers ───────────────────────────────────────────────────────────

    def effective_text(self) -> str:
        """Return full content if available, else snippet."""
        return self.content if self.content else self.snippet

    def to_dict(self) -> dict:
        return {
            "title":        self.title,
            "url":          self.url,
            "snippet":      self.snippet,
            "content":      self.content,
            "position":     self.position,
            "final_score":  self.final_score,
            "rerank_score": self.rerank_score,
            "pipeline_path": self.pipeline_path,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WebSearchResult":
        return cls(
            title         = d["title"],
            url           = d["url"],
            snippet       = d.get("snippet", ""),
            content       = d.get("content", ""),
            position      = d.get("position", 0),
            final_score   = d.get("final_score", 0.0),
            rerank_score  = d.get("rerank_score", 0.0),
            pipeline_path = d.get("pipeline_path", []),
        )


@dataclass
class WebSearchState:
    """
    Shared mutable state flowing through every stage of the pipeline.
    """
    # Input
    original_query: str

    # After QueryTransformStage
    rewritten_query: str = ""

    # After DuckDuckGoStage
    raw_results: List[WebSearchResult] = field(default_factory=list)

    # After FetchStage
    fetched_results: List[WebSearchResult] = field(default_factory=list)

    # After DeduplicationStage
    deduped_results: List[WebSearchResult] = field(default_factory=list)

    # Final output (after Rerank + Truncation)
    results: List[WebSearchResult] = field(default_factory=list)

    # Diagnostics
    cache_hit: bool = False
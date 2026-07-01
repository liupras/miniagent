#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-24
# @description: Web search pipeline — dynamically assembled from WebSearchConfig.
#
# Architecture
# ────────────
#   WebSearchPipeline           ← entry point, built from WebSearchConfig
#     ├── QueryTransformStage   ← query rewrite via LLM
#     ├── DuckDuckGoStage       ← fetch search result links
#     ├── FetchStage            ← crawl page content (httpx → Playwright fallback)
#     ├── DeduplicationStage    ← URL-level + content fingerprint dedup
#     ├── RerankStage           ← re-scores by relevance (cross-encoder / LLM / score)
#     ├── AdaptiveThresholdStage← drop results below mean − k·std
#     └── TruncationStage       ← token-aware text truncation + top-k trim
#
# Each stage is an async callable: WebSearchState → WebSearchState
# Pipeline.run() chains them, making it trivial to add / remove / swap stages.
#
# Guard rails
# ───────────
# - Query deduplication:  QueryTransformStage.run() normalises + dict.fromkeys()
# - Rate limiting:        RateLimiter (token bucket, shared across pipeline runs)
# - Result cache:         sha256(query) → serialised WebSearchResult list (TTL-aware)
#
# RerankMode
# ──────────
#   score   — sort by DuckDuckGo position score only (no model call)
#   bge     — BGEReranker with pluggable ScoringBackend (local / remote / ollama)
#   llm     — call LLM to score each result (most accurate, slowest)
#
# BGEReranker backends (configured via WebSearchConfig.reranker_config)
# ──────────────────────────────────────────────────────────────────────
#   {"backend": "local",  "model_name": "BAAI/bge-reranker-base"}
#   {"backend": "remote", "base_url": "http://localhost:9997/v1",   "model": "bge-reranker-v2-m3"}
#   {"backend": "ollama", "base_url": "http://localhost:11434/v1",  "model": "bge-large-zh"}
#
# Usage
# ─────
#   pipeline = WebSearchPipeline.from_config(cfg)
#   state    = await pipeline.run("最新的 Claude 模型有哪些功能？")
#   for r in state.results:
#       print(r.title, r.url, r.content[:200])

from __future__ import annotations

import asyncio
import hashlib
import re
import time
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from app.retrieval.reranker.factory import RerankerFactory
from app.retrieval.reranker.base import RerankMode
from app.infra.llm import LLMClient
from app.retrieval.adaptive_threshold import AdaptiveThresholdMixin
from app.infra.db.database import LLM,Tool

default_rewrite_prompt_template = "Please rewrite the following query into a concise, search-engine-optimised "
"keyword string (no explanation, output the query only):\n{query}"

from app.services.skill.web_search_models import WebSearchResult,WebSearchState
from app.services.skill.web_search_cache import SearchResultCache

# ═══════════════════════════════════════════════════════════════════════════
# Base Stage
# ═══════════════════════════════════════════════════════════════════════════

class BaseStage(ABC):
    """A single, composable search stage."""

    @abstractmethod
    async def run(self, state: WebSearchState) -> WebSearchState:
        raise NotImplementedError


# ═══════════════════════════════════════════════════════════════════════════
# Rate Limiter  (token bucket — shared across pipeline instances)
# ═══════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """
    Token-bucket rate limiter.

    Allows up to `burst` requests immediately, then refills at `rps` per second.
    All pipeline instances that share the same RateLimiter object will compete
    for the same bucket — useful to avoid hammering DDG from concurrent requests.
    """

    def __init__(self, rps: float = 1.0, burst: int = 3):
        self._rps    = rps
        self._burst  = burst
        self._tokens = float(burst)
        self._last   = time.monotonic()
        self._lock   = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(self._burst, self._tokens + elapsed * self._rps)
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            wait = (1.0 - self._tokens) / self._rps
            logger.debug(f"[RateLimiter] throttled — waiting {wait:.2f}s")
            await asyncio.sleep(wait)
            self._tokens = 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Stage 1 — QueryTransformStage
# ═══════════════════════════════════════════════════════════════════════════

class QueryTransformStage(BaseStage):
    """
    Rewrite the user query into a search-engine-optimised keyword string.

    Responsibilities:
    - Call LLM to produce a concise, search-friendly rewrite.
    - Normalise whitespace and collapse duplicate spaces.
    - Deduplicate: if rewrite == original (after normalisation), keep original.

    The stage always yields exactly one query (stored in state.rewritten_query).
    The original is preserved in state.original_query for later reranking.
    """

    def __init__(self, llm_client: LLMClient, model: str, prompt_template: str):
        self._llm           = llm_client
        self._model         = model
        self._prompt_template = prompt_template

    async def run(self, state: WebSearchState) -> WebSearchState:
        original = state.original_query.strip()
        prompt   = self._prompt_template.format_map({"query": original})

        resp = await asyncio.to_thread(
            self._llm.chat,
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature = 0.0
        )
        rewritten = str(resp).strip()

        # Deduplication: if semantically identical, keep original
        if self._normalise(original) == self._normalise(rewritten):
            rewritten = original

        state.rewritten_query = rewritten
        logger.debug(f"[QueryTransform] {original!r} → {rewritten!r}")
        return state

    @staticmethod
    def _normalise(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().lower()


# ═══════════════════════════════════════════════════════════════════════════
# Stage 2 — DuckDuckGoStage
# ═══════════════════════════════════════════════════════════════════════════

class DuckDuckGoStage(BaseStage):
    """
    Scrape DuckDuckGo HTML search results.

    Uses the stateless HTML endpoint (html.duckduckgo.com) which does not
    require JavaScript and is significantly more crawler-friendly than the
    main search page.

    Rate limiting is applied via the shared RateLimiter before each HTTP call.
    """

    _DDG_URL = "https://html.duckduckgo.com/html/"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml",
    }

    def __init__(
        self,
        rate_limiter: RateLimiter,
        max_results:  int   = 8,
        region:       str   = "cn-zh",
        safe_search:  str   = "moderate",
        timeout:      float = 10.0,
    ):
        self._limiter     = rate_limiter
        self._max_results = max_results
        self._region      = region
        self._safe_search = safe_search
        self._timeout     = timeout

    async def run(self, state: WebSearchState) -> WebSearchState:
        query = state.rewritten_query or state.original_query
        await self._limiter.acquire()

        try:
            results = await self._search(query)
        except Exception as exc:
            logger.error(f"[DDGStage] search failed: {exc}")
            results = []

        state.raw_results = results
        logger.debug(f"[DDGStage] query={query!r}  results={len(results)}")
        return state

    async def _search(self, query: str) -> List[WebSearchResult]:
        params = {
            "q":  query,
            "kl": self._region,
            "kp": {"off": "-2", "moderate": "-1", "strict": "1"}.get(
                self._safe_search, "-1"
            ),
        }
        async with httpx.AsyncClient(
            headers=self._HEADERS,
            follow_redirects=True,
            timeout=self._timeout,
        ) as client:
            resp = await client.post(self._DDG_URL, data=params)
            resp.raise_for_status()

        return self._parse(resp.text)

    def _parse(self, html: str) -> List[WebSearchResult]:
        soup    = BeautifulSoup(html, "html.parser")
        results = []

        for i, block in enumerate(soup.select(".result__body"), start=1):
            if i > self._max_results:
                break

            title_el   = block.select_one(".result__title a")
            snippet_el = block.select_one(".result__snippet")
            if not title_el:
                continue

            raw_href = title_el.get("href", "")
            real_url  = self._resolve_url(raw_href)
            if not real_url:
                continue

            results.append(WebSearchResult(
                title    = title_el.get_text(strip=True),
                url      = real_url,
                snippet  = snippet_el.get_text(strip=True) if snippet_el else "",
                position = i,
                final_score = 1.0 / i,       # inverse-rank as default score
                pipeline_path = ["ddg"],
            ))

        return results

    @staticmethod
    def _resolve_url(href: str) -> str:
        """Extract the true destination URL from DDG's redirect wrapper."""
        if not href:
            return ""
        if href.startswith("//duckduckgo.com/l/?"):
            parsed = urlparse("https:" + href)
            qs     = urllib.parse.parse_qs(parsed.query)
            return qs.get("uddg", [""])[0]
        if href.startswith("http"):
            return href
        return ""


# ═══════════════════════════════════════════════════════════════════════════
# Stage 3 — FetchStage
# ═══════════════════════════════════════════════════════════════════════════

class FetchStage(BaseStage):
    """
    Crawl the top-k URLs and extract main-body text.

    Strategy (per URL):
    1. httpx GET with a Googlebot UA → readability-style extraction.
    2. If content is too short and use_playwright=True → headless Chromium fallback.

    All fetches run concurrently (asyncio.gather) but are bounded by a
    semaphore to avoid exhausting file descriptors or triggering IP bans.
    """

    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }
    _MIN_CONTENT_LEN = 200   # chars; shorter → try playwright or give up

    def __init__(
        self,
        top_k:           int   = 5,
        timeout:         float = 10.0,
        max_content_len: int   = 8000,
        use_playwright:  bool  = False,
        concurrency:     int   = 3,
    ):
        self._top_k          = top_k
        self._timeout        = timeout
        self._max_content    = max_content_len
        self._use_playwright = use_playwright
        self._sem            = asyncio.Semaphore(concurrency)

    async def run(self, state: WebSearchState) -> WebSearchState:
        targets = state.raw_results[: self._top_k]
        fetched = await asyncio.gather(*[self._fetch_one(r) for r in targets])
        state.fetched_results = list(fetched)
        logger.debug(
            f"[FetchStage] fetched={len([r for r in fetched if r.content])}/"
            f"{len(targets)}"
        )
        return state

    async def _fetch_one(self, result: WebSearchResult) -> WebSearchResult:
        async with self._sem:
            try:
                content = await self._fetch_httpx(result.url)
                if len(content) < self._MIN_CONTENT_LEN and self._use_playwright:
                    content = await self._fetch_playwright(result.url)
                result.content = content[: self._max_content]
                if "fetch" not in result.pipeline_path:
                    result.pipeline_path.append("fetch")
            except Exception as exc:
                logger.warning(f"[FetchStage] {result.url} — {exc}")
                # Fallback: keep snippet as content
                result.content = result.snippet
        return result

    async def _fetch_httpx(self, url: str) -> str:
        async with httpx.AsyncClient(
            headers=self._HEADERS,
            follow_redirects=True,
            timeout=self._timeout,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        return self._extract_text(resp.text)

    async def _fetch_playwright(self, url: str) -> str:
        from playwright.async_api import async_playwright  # lazy import
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page    = await browser.new_page()
            await page.route(
                "**/*.{png,jpg,gif,webp,woff,woff2,svg}",
                lambda route: route.abort(),
            )
            await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            html = await page.content()
            await browser.close()
        return self._extract_text(html)

    @staticmethod
    def _extract_text(html: str) -> str:
        """
        Lightweight main-content extraction.

        Removes script / style / nav / header / footer elements, then collapses
        whitespace.  For production use, replace with readability-lxml:
            from readability import Document
            doc = Document(html); soup = BeautifulSoup(doc.summary(), ...)
        """
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer",
                         "aside", "form", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Stage 4 — DeduplicationStage
# ═══════════════════════════════════════════════════════════════════════════

class DeduplicationStage(BaseStage):
    """
    Remove duplicate and near-empty results.

    Two deduplication passes:
    1. URL-level: one result per (scheme + netloc + path) — strips query params
       and fragments that vary by tracking source but point to the same page.
    2. Content fingerprint: sha256 of the first 300 chars of effective_text().
       Catches mirror sites and syndicated articles.

    Results shorter than `min_content_len` are silently dropped.
    """

    def __init__(self, min_content_len: int = 100):
        self._min_len = min_content_len

    async def run(self, state: WebSearchState) -> WebSearchState:
        before = len(state.fetched_results)
        deduped = self._dedup(state.fetched_results)
        state.deduped_results = deduped
        logger.debug(f"[DeduplicationStage] {before} → {len(deduped)}")
        return state

    def _dedup(self, results: List[WebSearchResult]) -> List[WebSearchResult]:
        seen_urls:        set = set()
        seen_fingerprints: set = set()
        out: List[WebSearchResult] = []

        for r in results:
            # Drop near-empty results
            text = r.effective_text()
            if len(text) < self._min_len:
                continue

            # URL-level dedup (canonical form: scheme + netloc + path)
            parsed   = urlparse(r.url)
            url_key  = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
            if url_key in seen_urls:
                continue
            seen_urls.add(url_key)

            # Content fingerprint dedup
            fp = hashlib.sha256(text[:300].encode("utf-8")).hexdigest()
            if fp in seen_fingerprints:
                continue
            seen_fingerprints.add(fp)

            if "dedup" not in r.pipeline_path:
                r.pipeline_path.append("dedup")
            out.append(r)

        return out

# ═══════════════════════════════════════════════════════════════════════════
# Stage 5 — RerankStage
# ═══════════════════════════════════════════════════════════════════════════

class RerankStage(BaseStage):
    """
    Final scoring stage — behaviour is fully determined by RerankMode.
    """

    def __init__(
        self,        
        reranker  = RerankerFactory,
    ):
        self._reranker = reranker

    async def run(self, state: WebSearchState) -> WebSearchState:
        results = state.deduped_results
        if not results:
            state.results = results
            return state
        
        query = state.rewritten_query or state.original_query
        out = await self._reranker.run(query=query,chunks=results)

        logger.debug(
            f"[RerankStage] in={len(results)}  out={len(out)}"
        )
        state.results = out
        return state

# ═══════════════════════════════════════════════════════════════════════════
# Stage 6 — AdaptiveThresholdStage
# ═══════════════════════════════════════════════════════════════════════════

class AdaptiveThresholdStage(AdaptiveThresholdMixin, BaseStage):
    """
    Drop results whose final_score falls below  mean − std_factor × std.

    Filtering logic lives in AdaptiveThresholdMixin._apply_threshold()
    (shared with retrieval.py).  This class only wires state.results
    to the mixin and delegates to it.

    Requires at least 3 results to compute meaningful statistics; skips
    filtering otherwise.  Always keeps at least `min_keep` results.
    """

    def __init__(self, std_factor: float = 0.5, min_keep: int = 1):
        self._std_factor = std_factor
        self._min_keep   = min_keep

    async def run(self, state: WebSearchState) -> WebSearchState:
        state.results = self._apply_threshold(state.results)
        return state


# ═══════════════════════════════════════════════════════════════════════════
# Stage 7 — TruncationStage
# ═══════════════════════════════════════════════════════════════════════════

class TruncationStage(BaseStage):
    """
    Token-aware text truncation and final top-k trim.

    Two passes:
    1. Per-result: truncate result.content to max_chars_per_result at the
       nearest sentence boundary ('. ', '。', '! ', '? ') to avoid mid-sentence cuts.
    2. Global: accumulate char count across results; stop once max_total_chars
       is reached so the caller's context window is never exceeded.

    The stage also applies the final top_k cap (in case RerankStage returned more
    than needed — e.g. when AdaptiveThreshold relaxed the count).
    """

    def __init__(
        self,
        final_top_k:          int = 3,
        max_chars_per_result: int = 2000,
        max_total_chars:      int = 8000,
    ):
        self._top_k     = final_top_k
        self._per       = max_chars_per_result
        self._total_max = max_total_chars

    async def run(self, state: WebSearchState) -> WebSearchState:
        results   = state.results[: self._top_k]
        out       = []
        total     = 0

        for r in results:
            r.content = self._truncate_at_sentence(r.content, self._per)
            text_len  = len(r.effective_text())

            if total + text_len > self._total_max and out:
                # One more result would overflow; keep what we have
                break

            if "trunc" not in r.pipeline_path:
                r.pipeline_path.append("trunc")
            out.append(r)
            total += text_len

        logger.debug(
            f"[TruncationStage] results={len(out)}  total_chars={total}"
        )
        state.results = out
        return state

    @staticmethod
    def _truncate_at_sentence(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        # Try to cut at the last sentence boundary before the limit
        candidate = text[:limit]
        for sep in (". ", "。", "! ", "? ", "！", "？", "\n"):
            idx = candidate.rfind(sep)
            if idx > limit // 2:   # only if the cut point is in the second half
                return candidate[: idx + len(sep)].rstrip()
        return candidate.rstrip()


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class WebSearchConfig:
    """
    Flat, typed snapshot of all parameters needed to run the web search pipeline.
    """
    # Query transform
    enable_query_rewrite:  bool  = True

    # DuckDuckGo
    ddg_max_results:       int   = 8      # links to fetch from DDG
    ddg_region:            str   = "cn-zh"
    ddg_safe_search:       str   = "moderate"

    # Fetch
    fetch_top_k:           int   = 5      # pages to actually crawl
    fetch_timeout:         float = 10.0
    fetch_max_content_len: int   = 8000   # chars per page before truncation
    use_playwright:        bool  = False  # enable JS-render fallback

    # Rate limiting (token bucket)
    rate_limit_rps:        float = 1.0    # max requests per second to DDG
    rate_limit_burst:      int   = 3      # burst capacity

    # Cache
    enable_cache:          bool  = True
    cache_ttl_seconds:     int   = 3600
    cache_max_size:        int   = 256

    # Deduplication
    dedup_min_content_len: int   = 100    # ignore near-empty pages

    # Rerank
    # reranker_config drives BGEReranker.from_config(); ignored when rerank_mode=score/llm.
    # Examples:
    #   {"backend": "local",  "model_name": "BAAI/bge-reranker-v2-m3"}
    #   {"backend": "remote", "base_url": "http://localhost:9997/v1", "model": "bge-reranker-v2-m3"}
    #   {"backend": "ollama", "base_url": "http://localhost:11434/v1", "model": "bge-large-zh"}
    rerank_mode:           RerankMode = RerankMode.SCORE
    rerank_top_k:          int = 3

    # Truncation
    final_top_k:           int   = 2
    max_chars_per_result:  int   = 2000
    max_total_chars:       int   = 8000

    @classmethod
    def create(cls,             
        config              : dict = {},   
    ) -> "WebSearchConfig": 

        try:
            ranking_mode = RerankMode(
                config.get("rerank_mode", RerankMode.SCORE.value)
            )
        except ValueError:
            logger.warning(
                "Unknown reranking_mode, using 'Score'."
            )
            ranking_mode = RerankMode.SCORE

        return cls(
            enable_query_rewrite = config.get("enable_query_rewrite", True),

            ddg_max_results = config.get("ddg_max_results", 8),
            ddg_region = config.get( "ddg_region", "cn-zh"),
            ddg_safe_search = config.get( "ddg_safe_search", "moderate"),

            fetch_top_k = config.get( "fetch_top_k", 5),
            fetch_timeout =  config.get( "fetch_timeout", 10.0),
            fetch_max_content_len = config.get( "fetch_max_content_len", 1000),
            use_playwright = config.get( "use_playwright", False),

            rate_limit_rps = config.get( "rate_limit_rps", 1.0),
            rate_limit_burst = config.get( "rate_limit_rps", 3),

            enable_cache = config.get( "enable_cache", True),
            cache_ttl_seconds = config.get( "cache_ttl_seconds", 3600),
            cache_max_size = config.get( "cache_max_size", 256),

            dedup_min_content_len = config.get( "dedup_min_content_len", 100),

            rerank_mode = ranking_mode,
            rerank_top_k = config.get( "rerank_top_k", 3),

            final_top_k = config.get( "final_top_k", 2),
            max_chars_per_result = config.get( "max_chars_per_result", 2000),
            max_total_chars = config.get( "max_total_chars", 8000)
        )

class WebSearchPipeline:
    """
    Assembles and executes a web search pipeline from a WebSearchConfig.

    Topology
    ────────
    QueryTransformStage  →  DuckDuckGoStage  →  FetchStage
        →  DeduplicationStage  →  RerankStage  →  AdaptiveThresholdStage
        →  TruncationStage

    Cache behaviour
    ───────────────
    The complete result list is cached keyed by sha256(rewritten_query).
    A cache hit skips all stages after QueryTransformStage.
    Cache is disabled when enable_cache=False in WebSearchConfig.
    """

    def __init__(self, stages: List[BaseStage], cache: Optional[SearchResultCache] = None):
        self._stages = stages
        self._cache  = cache

    # ── factory ──────────────────────────────────────────────────────────

    @classmethod
    async def create(
        cls,         
        tool_config:    Tool,
        llm_config:     LLM,
        query_rewrite_web_search_prompt_template:str
    ) -> "WebSearchPipeline":
        """Build a fully-configured pipeline from a WebSearchConfig.""" 
        
        config = tool_config.config or {}
        cfg  = WebSearchConfig.create(
            config=config,            
        )        
        
        # ── Stages ────────────────────────────────────────────────────────
        stages: List[BaseStage] = []

        if cfg.enable_query_rewrite:             
            llm_client = LLMClient(
                base_url = llm_config.base_url,
                api_key=llm_config.api_key,
                temperature=llm_config.temperature,
            )
            stages.append(QueryTransformStage(
                llm_client=         llm_client,
                model    =          llm_config.model_name,
                prompt_template=    query_rewrite_web_search_prompt_template
            ))

        rate_limiter = RateLimiter(rps=cfg.rate_limit_rps, burst=cfg.rate_limit_burst)
        stages.append(DuckDuckGoStage(
            rate_limiter = rate_limiter,
            max_results  = cfg.ddg_max_results,
            region       = cfg.ddg_region,
            safe_search  = cfg.ddg_safe_search,
            timeout      = cfg.fetch_timeout,
        ))

        stages.append(FetchStage(
            top_k          = cfg.fetch_top_k,
            timeout        = cfg.fetch_timeout,
            max_content_len = cfg.fetch_max_content_len,
            use_playwright = cfg.use_playwright,
        ))

        stages.append(DeduplicationStage(
            min_content_len = cfg.dedup_min_content_len,
        ))

        reranker_config = config.get("reranker", {})

        reranker = RerankerFactory.create(
            mode=cfg.rerank_mode,
            top_k=cfg.rerank_top_k,
            reranker_config=reranker_config,
            llm_config=llm_config
        )
        stages.append(RerankStage(            
            reranker = reranker,
        ))

        stages.append(AdaptiveThresholdStage(
            std_factor = 0.5,
            min_keep   = 1,
        ))

        stages.append(TruncationStage(
            final_top_k          = cfg.final_top_k,
            max_chars_per_result = cfg.max_chars_per_result,
            max_total_chars      = cfg.max_total_chars,
        ))

        # ── Cache ────────────────────────────────────────────────────────
        cache: Optional[SearchResultCache] = None
        if cfg.enable_cache:
            cache = SearchResultCache(max_size=cfg.cache_max_size, ttl=cfg.cache_ttl_seconds)
            logger.info("[Pipeline] cache enabled  "
                        f"max_size={cfg.cache_max_size}  ttl={cfg.cache_ttl_seconds}s")

        return cls(stages=stages, cache=cache)

    # ── run ───────────────────────────────────────────────────────────────

    async def run(self, query: str) -> WebSearchState:
        """
        Execute the full pipeline for a query.

        Cache behaviour
        ───────────────
        Cache is keyed by the *rewritten* query (produced by QueryTransformStage).
        QueryTransformStage always runs first so the cache key is stable across
        minor phrasing variations in the original query.
        A cache hit populates state.results and sets state.cache_hit = True,
        skipping all remaining stages.
        """
        state = WebSearchState(original_query=query.strip())

        if not state.original_query:
            return state

        # Always run query transform first (needed for cache key)
        transform_stages = [s for s in self._stages if isinstance(s, QueryTransformStage)]
        remaining_stages = [s for s in self._stages if not isinstance(s, QueryTransformStage)]

        if transform_stages:
            for stage in transform_stages:
                state = await stage.run(state)
        else:
            # No rewrite stage — treat original query as the rewritten query
            state.rewritten_query = state.original_query

        # ── cache read ────────────────────────────────────────────────────
        cache_key = state.rewritten_query or state.original_query
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug(
                    f"[Pipeline] cache hit  query={cache_key[:60]!r}"
                )
                state.results    = cached
                state.cache_hit  = True
                return state
            logger.debug(f"[Pipeline] cache miss  query={cache_key[:60]!r}")

        logger.info(
            f"[Pipeline] original={query[:60]!r}  "
            f"rewritten={state.rewritten_query[:60]!r}"
        )

        for stage in remaining_stages:
            state = await stage.run(state)

        # ── cache write ───────────────────────────────────────────────────
        if self._cache is not None and state.results:
            self._cache.set(cache_key, state.results)
            logger.debug(f"[Pipeline] cached  query={cache_key[:60]!r}")

        return state

    # ── helpers ───────────────────────────────────────────────────────────

    def get_cache_stats(self) -> Optional[dict]:
        """Return cache statistics, or None if cache is disabled."""
        return self._cache.stats() if self._cache else None

    def clear_cache(self) -> None:
        """Manually evict all cached results."""
        if self._cache:
            self._cache.clear()
            logger.info("[Pipeline] cache cleared")

    @staticmethod
    def format_for_llm(state: WebSearchState) -> str:
        """
        Render pipeline output as a plain-text context block suitable for
        injection into an LLM prompt.

        Example output:

            [1] Some Article Title
            Source: https://example.com/article
            Score: 0.87

            First two thousand characters of the article body…

            ---

            [2] …
        """
        if not state.results:
            return "No search results found."

        parts = []
        for i, r in enumerate(state.results, 1):
            parts.append(
                f"[{i}] {r.title}\n"
                f"Source: {r.url}\n"
                f"Score: {r.final_score:.3f}\n\n"
                f"{r.effective_text()}"
            )
        return "\n\n---\n\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# Quick smoke test
# ═══════════════════════════════════════════════════════════════════════════

async def _demo():
    """
    End-to-end smoke test for WebSearchPipeline.

    Runs five scenarios in sequence so you can verify each subsystem without
    needing a full test harness.  Each mode prints a compact summary so you
    can spot regressions at a glance.

    Modes covered
    ─────────────
    1. SCORE  — fastest path, no reranker, no query rewrite
    2. SCORE  — with query rewrite via local Ollama LLM
    3. BGE    — local BGE reranker  (commented out; requires local model)
    4. BGE    — remote reranker     (commented out; requires running server)
    5. LLM    — per-chunk LLM reranker  (commented out; requires local Ollama)
    6. LLM    — batch LLM reranker      (commented out; requires local Ollama)

    After Mode 1 we run the same query again to verify cache hit behaviour.
    """

    QUERY = "Claude Sonnet latest features"

    def _print_state(label: str, state: WebSearchState) -> None:
        """Print a compact one-line summary per result."""
        print(f"\n{'═' * 60}")
        print(f"  {label}")
        print(f"  cache_hit={state.cache_hit}  results={len(state.results)}")
        print(f"{'═' * 60}")
        if not state.results:
            print("  ⚠  No results returned.")
            return
        for i, r in enumerate(state.results, 1):
            snippet = r.effective_text()[:120].replace("\n", " ")
            print(f"  [{i}] score={r.final_score:.3f}  path={r.pipeline_path}")
            print(f"       {r.title[:70]!r}")
            print(f"       {r.url}")
            print(f"       {snippet!r}")
        print()

    def _assert(condition: bool, msg: str) -> None:
        if condition:
            print(f"  ✓ {msg}")
        else:
            print(f"  ✗ FAIL: {msg}")

    
    # ── Mode 1: SCORE — no rewriter (fastest) ────────────────────────────
    print("\n[Mode 1] SCORE, no query rewrite, cache enabled")
    cfg1 = WebSearchConfig(
        enable_query_rewrite = False,
        rerank_mode          = RerankMode.SCORE,
        ddg_max_results      = 6,
        fetch_top_k          = 4,
        rerank_top_k         = 4,
        final_top_k          = 3,
        enable_cache         = True,
        cache_ttl_seconds    = 60,
    )
    pipeline1 = WebSearchPipeline.create(cfg1)
    state1    = await pipeline1.run(QUERY)
    _print_state("Mode 1 — first call", state1)
    _assert(not state1.cache_hit,     "first call is NOT a cache hit")
    _assert(len(state1.results) > 0,  "returned at least one result")
    _assert(state1.results == sorted(state1.results,
            key=lambda r: r.final_score, reverse=True),
            "results are sorted by final_score descending")
    
    # ── Cache hit: same pipeline, same query ─────────────────────────────
    print("\n[Mode 1 — cache hit check]")
    state1b = await pipeline1.run(QUERY)
    _print_state("Mode 1 — second call (expect cache hit)", state1b)
    _assert(state1b.cache_hit,        "second call IS a cache hit")
    _assert(
        [r.url for r in state1b.results] == [r.url for r in state1.results],
        "cached results are identical to first-call results",
    )
    print(f"  Cache stats: {pipeline1.get_cache_stats()}")
    
    # ── Mode 2: SCORE — with query rewrite and reranker ───────────────────────────────
    print("\n[Mode 2] SCORE + query rewrite via local Ollama")
    cfg2 = WebSearchConfig(
        enable_query_rewrite = True,
        llm_base_url         = "http://localhost:11434/v1",
        llm_api_key          = "ollama",
        llm_model            = "qwen3:4b",
        rerank_mode          = RerankMode.BGE,
        reranker_config={"backend": "local", "model_name": "bge-reranker-base", "max_length": 512, "batch_size": 64},
        ddg_max_results      = 6,
        fetch_top_k          = 4,
        rerank_top_k         = 4,
        final_top_k          = 3,
        enable_cache         = False,   # disable cache so we always hit the LLM
    )
    try:
        pipeline2 = WebSearchPipeline.create(cfg2)
        state2    = await pipeline2.run(QUERY)
        _print_state("Mode 2 — SCORE + rewrite", state2)
        _assert(bool(state2.rewritten_query), "rewritten_query is non-empty")
        _assert(len(state2.results) > 0,      "returned at least one result")
    except Exception as exc:
        print(f"  ⚠  Mode 2 skipped ({exc})")
    
    # ── LLM output (Mode 1 results formatted for injection) ───────────────
    print("\n[format_for_llm output — Mode 1 results]")
    print(WebSearchPipeline.format_for_llm(state2))


if __name__ == "__main__":
    asyncio.run(_demo())
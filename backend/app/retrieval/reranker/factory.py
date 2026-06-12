#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-26
# @description: reranker main class

from loguru import logger

from app.retrieval.reranker.base import RerankMode,Scorable
from typing import Optional,List
from app.infra.db.database import LLM
from app.retrieval.reranker.bge import BGEReranker
from app.retrieval.reranker.llm import LLMReranker
from app.infra.llm import LLMClient

class RerankerFactory:
    """Reranker class"""

    def __init__(
        self,
        mode    :RerankMode,
        top_k   :int = 3,
        reranker:       BGEReranker|LLMReranker|None = None,
    ):
        self._mode = mode
        self._top_k = top_k
        self._reranker = reranker

    @classmethod
    def create(
        cls,
        mode            :RerankMode,
        top_k           :int = 3,
        reranker_config :Optional[dict] = None,
        llm_config      :LLM = None,
    ):
        if mode != RerankMode.SCORE and not reranker_config:
            raise ValueError("[Reranker] config is empty")

        if mode == RerankMode.BGE:
            try:
                backend = reranker_config.get("backend", "local")

                if backend == "local":
                    reranker = BGEReranker.local(
                        model_name = reranker_config.get("model_name", "BAAI/bge-reranker-base"),
                        device     = reranker_config.get("device"),
                        max_length = reranker_config.get("max_length", 512),
                        batch_size = reranker_config.get("batch_size", 64),
                        cache_dir  = reranker_config.get("cache_dir"),
                    )

                elif backend == "remote":
                    client = LLMClient(
                        base_url = llm_config.base_url,
                        api_key=llm_config.api_key,
                        temperature=llm_config.temperature,
                    )
                    reranker = BGEReranker.remote(
                        client     = client,
                        model      = llm_config.model_name,
                        batch_size = reranker_config.get("batch_size", 100),
                        timeout    = reranker_config.get("timeout", 30.0),
                    )

                elif backend == "ollama":
                    client = LLMClient(
                        base_url = llm_config.base_url,
                        api_key=None,
                        temperature=llm_config.temperature,
                    )
                    reranker = BGEReranker.ollama(
                        client         = client,
                        model          = llm_config.get("model", "bge-large-zh"),
                        query_prefix   = reranker_config.get("query_prefix", ""),
                        passage_prefix = reranker_config.get("passage_prefix", ""),
                        batch_size     = reranker_config.get("batch_size", 64),
                    )

                else:
                    raise ValueError(f"[Reranker] Unknown reranker backend: {backend!r}")

                logger.info(
                    f"[Reranker] auto-built  "
                    f"backend={reranker_config.get('backend')}  "
                )
                return cls(
                    mode = mode,
                    top_k = top_k,
                    reranker = reranker
                )

            except Exception as exc:
                # Build failures do not halt the pipeline; RerankStage will automatically downgrade to hybrid.
                logger.warning(
                    f"[Reranker] build failed: {exc}  "
                    f"— RerankStage will degrade to hybrid"
                )
        elif mode == RerankMode.LLM:
            llm_client = LLMClient(
                base_url=llm_config.base_url,
                api_key=llm_config.api_key,
                temperature=llm_config.temperature,
            )
            reranker = LLMReranker(client=llm_client,model=llm_config.model_name)

            return cls(
                    mode = mode,
                    top_k = top_k,
                    reranker = reranker
                )
        else:
            return cls(
                    mode = RerankMode.SCORE,
                    top_k = top_k,
                    reranker = None
                )
        
    def _resolve_mode(self) -> RerankMode:
        """Degrade gracefully if the required reranker is missing."""
        mode = self._mode
        if mode in (RerankMode.BGE, RerankMode.LLM) and self._reranker is None:
            logger.warning(
                f"[Reranker] mode={mode.value} but no reranker provided "
                "— falling back to mode=score"
            )
            mode = RerankMode.SCORE
        return mode
    
    async def run(
        self,
        query:  str,
        chunks: List[Scorable]
    )->List[Scorable]:
        
        mode = self._resolve_mode()

        if mode == RerankMode.SCORE:
            out = sorted(chunks, key=lambda r: r.final_score, reverse=True)
            out = out[: self._top_k]
            return out
        elif self._reranker:    # BGE or LLM
            out = await self._reranker.rerank(
                query   = query,
                chunks  =chunks,
                top_k   = self._top_k,
            )
        else:
            out=[]
            logger.warning(
                f"[Reranker] mode={mode.value} is not working"
            )
        return out

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: KnowledgeBase Database Management (Asynchronous Version)

from typing import List, Optional

from loguru import logger
from sqlalchemy import select

from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import KnowledgeBase, StrategyConfig, Embedding, LLM


class AsyncKnowledgeBaseDatabase(AsyncBaseDatabase):
    """KnowledgeBase table operations - Asynchronous Version"""

    async def get_kb(self, kb_id: int) -> Optional[KnowledgeBase]:
        async with self.get_session() as session:
            return await session.get(KnowledgeBase, kb_id)

    async def kb_exists(self, kb_id: int) -> bool:
        kb = await self.get_kb(kb_id)
        return kb is not None

    async def get_active_strategy_config(self, kb_id: int) -> Optional[StrategyConfig]:
        """
        Return the active StrategyConfig for a knowledge base.

        A KB should have at most one active config (is_active=True) at any
        given time.  If none is found, None is returned and the caller should
        fall back to sensible defaults.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(StrategyConfig)
                .where(
                    StrategyConfig.kb_id == kb_id,
                    StrategyConfig.is_active == True,   # noqa: E712
                )
                .limit(1)
            )
            row = result.scalar_one_or_none()

        if row is None:
            logger.warning(
                f"[DB] No active StrategyConfig found for kb_id={kb_id}"
            )
        else:
            logger.debug(
                f"[DB] Active StrategyConfig: kb_id={kb_id} "
                f"config_id={row.config_id} version={row.version}"
            )
        return row

    async def get_all_strategy_configs(self, kb_id: int) -> List[StrategyConfig]:
        """
        Return all StrategyConfig rows for a knowledge base, ordered by
        version descending (latest first).
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(StrategyConfig)
                .where(StrategyConfig.kb_id == kb_id)
                .order_by(StrategyConfig.version.desc())
            )
            rows = result.scalars().all()

        logger.debug(
            f"[DB] get_all_strategy_configs: kb_id={kb_id} "
            f"found={len(rows)}"
        )
        return list(rows)

    async def get_embedding_by_kb_id(self, kb_id: int) -> Optional[Embedding]:
        """
        Return the Embedding configuration associated with a knowledge base.
        """
        async with self.get_session() as session:
            kb = await session.get(KnowledgeBase, kb_id)

            if kb is None:
                logger.warning(
                    f"[DB] get_embedding_by_kb_id: KnowledgeBase not found kb_id={kb_id}"
                )
                return None

            if kb.embedding_provider is None:
                logger.warning(
                    f"[DB] get_embedding_by_kb_id: no embedding_provider set for kb_id={kb_id}"
                )
                return None

            embedding = await session.get(Embedding, kb.embedding_provider)

        if embedding is None:
            logger.warning(
                f"[DB] get_embedding_by_kb_id: Embedding record not found "
                f"kb_id={kb_id} embedding_provider={kb.embedding_provider}"
            )
        else:
            logger.debug(
                f"[DB] get_embedding_by_kb_id: kb_id={kb_id} "
                f"embedding={embedding.name} model={embedding.model_name}"
            )
        return embedding
    
    async def get_llm_by_kb_id(self, kb_id: int) -> Optional[LLM]:
        """
        Return the LLM configuration associated with a knowledge base.
        """
        async with self.get_session() as session:
            kb = await session.get(KnowledgeBase, kb_id)

            if kb is None:
                logger.warning(
                    f"[DB] get_llm_by_kb_id: KnowledgeBase not found kb_id={kb_id}"
                )
                return None

            if kb.llm_provider is None:
                logger.warning(
                    f"[DB] get_llm_by_kb_id: no llm_provider set for kb_id={kb_id}"
                )
                return None

            llm = await session.get(LLM, kb.llm_provider)

        if llm is None:
            logger.warning(
                f"[DB] get_llm_by_kb_id: LLM record not found "
                f"kb_id={kb_id} llm_provider={kb.llm_provider}"
            )
        else:
            logger.debug(
                f"[DB] get_llm_by_kb_id: kb_id={kb_id} "
                f"llm_id={llm.id} provider={llm.provider_name} model={llm.model_name}"
            )
        return llm
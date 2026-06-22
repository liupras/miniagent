#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: KnowledgeBase Database Management (Asynchronous Version)

from typing import List, Optional

from loguru import logger
from sqlalchemy import delete, func, select, update

from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import KnowledgeBase, StrategyConfig, Embedding, LLM,Document


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

            if kb.llm_id is None:
                logger.warning(
                    f"[DB] get_llm_by_kb_id: no llm_id set for kb_id={kb_id}"
                )
                return None

            llm = await session.get(LLM, kb.llm_id)

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
    
    async def list_kbs(
        self,
        page: int = 1,
        page_size: int = 20,
        name_filter: str | None = None,
        domain_id: int | None = None,
        is_active: bool | None = None
    ) -> tuple[int, List[KnowledgeBase]]:
        """List knowledge bases with pagination and filters."""
        async with self.get_session() as session:
            base_q = select(KnowledgeBase)            

            if name_filter:
                base_q = base_q.where(KnowledgeBase.name.contains(name_filter))
            if domain_id is not None:
                base_q = base_q.where(KnowledgeBase.domain_id == domain_id)
            if is_active is not None:
                base_q = base_q.where(KnowledgeBase.is_active == is_active)
            
            total_result = await session.execute(
                select(func.count()).select_from(base_q.subquery())
            )
            total: int = total_result.scalar_one()

            rows_result = await session.execute(
                base_q.order_by(KnowledgeBase.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            items = list(rows_result.scalars().all())
            return total, items

    async def create_kb(self, data: dict) -> KnowledgeBase:
        """Create a new knowledge base."""
        async with self.get_session() as session:
            obj = KnowledgeBase(**data)
            session.add(obj)
            return obj

    async def update_kb(self, kb_id: int, data: dict) -> Optional[KnowledgeBase]:
        """Update a knowledge base."""
        async with self.get_session() as session:
            result = await session.execute(
                update(KnowledgeBase)
                .where(KnowledgeBase.id == kb_id)
                .values(**data)
            )
            
            if result.rowcount == 0:
                return None                

            updated_kb = await session.get(KnowledgeBase, kb_id)
            return updated_kb

    async def delete_kb(self, kb_id: int) -> bool:
        """Delete a knowledge base."""
        async with self.get_session() as session:
            result = await session.execute(
                delete(KnowledgeBase).where(KnowledgeBase.id == kb_id)
            )
            return result.rowcount > 0

    async def get_kb_options(self) -> List[dict]:
        """Get knowledge base options for dropdown selection."""
        async with self.get_session() as session:
            result = await session.execute(
                select(KnowledgeBase.id, KnowledgeBase.name)
                .order_by(KnowledgeBase.name)
            )
            return [{"id": row[0], "name": row[1]} for row in result.fetchall()]

    async def toggle_kb_active(self, kb_id: int) -> bool:
        """Toggle the active status of a knowledge base."""
        async with self.get_session() as session:
            kb = await session.get(KnowledgeBase, kb_id)
            if kb is None:
                return False
            kb.is_active = not kb.is_active
            await session.commit()
            return True

    async def get_kb_stats(self, kb_id: int) -> dict:
        """Get statistics for a knowledge base."""
        async with self.get_session() as session:
            kb = await session.get(KnowledgeBase, kb_id)
            if not kb:
                return {}
            
            doc_result = await session.execute(
                select(func.count()).where(Document.kb_id == kb_id)
            )
            doc_count = doc_result.scalar_one()
            
            chunk_count = kb.chunk_count or 0
            
            return {
                "id": kb.id,
                "name": kb.name,
                "document_count": doc_count,
                "chunk_count": chunk_count,
                "created_at": kb.created_at,
                "updated_at": kb.updated_at,
                "is_active": kb.is_active
            }
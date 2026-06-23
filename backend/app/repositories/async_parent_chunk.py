#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: ParentChunk Database Management (Asynchronous Version)

from typing import Dict, List, Tuple

from loguru import logger
from sqlalchemy import func, select, delete
from sqlalchemy.orm import selectinload

from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import ParentChunk

class AsyncParentChunkDatabase(AsyncBaseDatabase):
    """ParentChunk table operations - Asynchronous Version"""

    async def filter_new_parent_chunks(
        self,
        kb_id: int,
        parent_chunks: List[ParentChunk],
    ) -> Tuple[List[ParentChunk], Dict[int, int]]:
        """
        Dedup parent chunks against existing KB rows.

        Returns
        -------
        new_parents   : ParentChunk objects that do NOT yet exist in SQLite
                        → pass these to save_parent_chunks()
        index_to_id   : {chunk_index → existing_db_id} for already-stored parents
                        → merge with new IDs to build the full parent_index_to_id map
        """
        if not parent_chunks:
            return [], {}

        async with self.get_session() as session:
            hashes = [pc.hash_value for pc in parent_chunks]

            result = await session.execute(
                select(ParentChunk.hash_value, ParentChunk.id).where(
                    ParentChunk.kb_id == kb_id,
                    ParentChunk.hash_value.in_(hashes),
                )
            )
            rows = result.all()

        existing_hash_to_id: Dict[str, int] = {row[0]: row[1] for row in rows}

        new_parents: List[ParentChunk] = []
        index_to_id: Dict[int, int] = {}  # chunk_index → existing db id

        for pc in parent_chunks:
            if pc.hash_value in existing_hash_to_id:
                index_to_id[pc.chunk_index] = existing_hash_to_id[pc.hash_value]
                logger.debug(
                    f"[DB] ParentChunk dedup: index={pc.chunk_index} "
                    f"hash={pc.hash_value[:8]}… → existing id={index_to_id[pc.chunk_index]}"
                )
            else:
                new_parents.append(pc)

        skipped = len(parent_chunks) - len(new_parents)
        if skipped:
            logger.debug(f"[DB] ParentChunk dedup: {skipped} duplicate(s) skipped.")

        return new_parents, index_to_id

    async def save_parent_chunks(
        self, parent_chunks: List[ParentChunk]
    ) -> None:
        """
        Bulk-insert new parent chunks asynchronously.
        Note: The context manager in AsyncBaseDatabase handles commit/rollback.
        """
        if not parent_chunks:
            return
            
        async with self.get_session() as session:
            session.add_all(parent_chunks)
            # Use flush to ensure that the ID is populated into the object, 
            # but do not immediately commit the entire transaction.
            await session.flush()
            
        logger.debug(f"[DB] Saved {len(parent_chunks)} new parent chunks.")

    async def get_texts_by_ids(self, parent_ids: List[int]) -> Dict[int, str]:
        """
        Batch-fetch the text of ParentChunk rows by their primary-key IDs asynchronously.
        """
        if not parent_ids:
            return {}

        async with self.get_session() as session:
            result = await session.execute(
                select(ParentChunk.id, ParentChunk.text).where(
                    ParentChunk.id.in_(parent_ids)
                )
            )
            rows = result.all()

        res_dict: Dict[int, str] = {pid: text for pid, text in rows}
        logger.debug(
            f"[DB] get_texts_by_ids: requested={len(parent_ids)} "
            f"found={len(res_dict)}"
        )
        return res_dict

    async def delete_by_doc(self, doc_id: int) -> None:
        """
        Delete all ParentChunk rows for a document asynchronously.
        Recommended: Use direct delete query to avoid issues with uninitialized lazy-loading in async.
        """
        async with self.get_session() as session:
            # Using the delete statement directly better meets the atomicity requirements of asynchronous operations.
            stmt = delete(ParentChunk).where(ParentChunk.doc_id == doc_id)
            await session.execute(stmt)
            # Note: If SQLAlchemy-level cascading deletes exist and ON DELETE CASCADE is not configured,
            # you may need to decide whether to load the delete or execute the SQL directly based on the specific business logic.
            
        logger.debug(f"[DB] Deleted parent chunks for doc id={doc_id}")


    async def get_parent_chunks_by_doc(
        self, doc_id: int, page: int, page_size: int
    ) -> tuple[list[ParentChunk], int]:
        async with self.get_session() as session:
            total = await session.scalar(
                select(func.count())
                .select_from(ParentChunk)
                .where(ParentChunk.doc_id == doc_id)
            )

            stmt = (
                select(ParentChunk)
                .where(ParentChunk.doc_id == doc_id)
                .options(selectinload(ParentChunk.chunks))
                .order_by(ParentChunk.chunk_index)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            result = await session.execute(stmt)
            parents = list(result.scalars().all())

            # `selectinload` does not guarantee the order of sub-blocks; here, they are explicitly sorted by `chunk_index`.
            for p in parents:
                p.chunks.sort(key=lambda c: c.chunk_index)

            return parents, total or 0
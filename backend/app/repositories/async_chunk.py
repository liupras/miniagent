#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: Chunk Database Management (Async Version)

from typing import Dict, List, Optional

from loguru import logger
from sqlalchemy import select, insert
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError

from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import Chunk, Document

class AsyncChunkDatabase(AsyncBaseDatabase):

    # =========================================================================
    # Queries (Async)
    # =========================================================================

    async def get_chunk_ids_by_doc(self, doc_id: int) -> List[int]:
        """Return the SQLite IDs of all child chunks belonging to a document."""
        async with self.get_session() as session:
            # In asynchronous mode, doc.chunks cannot be accessed directly.
            stmt = select(Chunk.id).where(Chunk.doc_id == doc_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_chunks_by_kb(
        self,
        kb_id: int,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Chunk]:
        async with self.get_session() as session:
            stmt = select(Chunk).where(Chunk.kb_id == kb_id)
            if offset is not None:
                stmt = stmt.offset(offset)
            if limit is not None:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # =========================================================================
    # Deduplication
    # =========================================================================

    async def filter_new_chunks(self, kb_id: int, chunks: List[Chunk]) -> List[Chunk]:
        """
        Return only chunks whose hash_value does not yet exist in this KB.
        Prevents duplicate child chunks during partial re-indexing.
        """
        if not chunks:
            return chunks

        async with self.get_session() as session:
            hashes = [c.hash_value for c in chunks]
            stmt = select(Chunk.hash_value).where(
                Chunk.kb_id == kb_id,
                Chunk.hash_value.in_(hashes),
            )
            result = await session.execute(stmt)
            existing = set(result.scalars().all())

        unique = [c for c in chunks if c.hash_value not in existing]
        skipped = len(chunks) - len(unique)
        if skipped:
            logger.debug(f"[DB] Chunk dedup: {skipped} duplicate(s) skipped.")
        return unique

    # =========================================================================
    # Writes (Async)
    # =========================================================================

    async def save_chunks(
        self,
        chunks: List[Chunk],
        parent_index_to_id: Dict[int, int],
    ) -> None:
        """
        Link each child chunk to its parent via parent_index_to_id, then
        bulk-insert.

        Uses flush so IDs are populated without committing the transaction.
        The caller is responsible for the final commit.
        """
        if not chunks:
            return

        async with self.get_session() as session:
            try:
                for sc in chunks:
                    # _extra_metadata is an allowed temporary attribute in the Chunk model definition.
                    pidx = getattr(sc, "_extra_metadata", {}).get("parent_index", 0)
                    sc.parent_id = parent_index_to_id.get(pidx)

                session.add_all(chunks)
                await session.flush()
            except SQLAlchemyError:
                raise

        logger.debug(f"[DB] Saved {len(chunks)} child chunks.")

    async def bulk_insert_chunks(self, chunks: List[Dict]) -> int:
        """
        Bulk insert chunks from plain dicts.
        Triggers ORM events; safer for general use.
        """
        if not chunks:
            return 0
        async with self.get_session() as session:
            objects = [Chunk(**data) for data in chunks]
            session.add_all(objects)
            await session.flush()
            return len(objects)

    async def bulk_insert_chunks_fast(self, chunks: List[Dict]) -> int:
        """
        High-performance batch inserts. Use the async version of the insert statement.
        """
        if not chunks:
            return 0
        async with self.get_session() as session:
            await session.execute(insert(Chunk), chunks)
            return len(chunks)

    async def get_texts_by_ids(self, chunk_ids: List[int]) -> Dict[int, str]:
        """
        Batch-fetch chunk texts by SQLite Chunk.id.
        Returns {chunk_id: text} for all found rows; missing IDs are omitted.
        Used by TextHydrationStage to back-fill vector-only results.
        """
        if not chunk_ids:
            return {}

        async with self.get_session() as session:
            stmt = select(Chunk.id, Chunk.text).where(Chunk.id.in_(chunk_ids))
            result = await session.execute(stmt)
            rows = result.all()

        res_dict = {row[0]: row[1] for row in rows}
        missing = len(chunk_ids) - len(res_dict)
        if missing:
            logger.warning(f"[DB] get_texts_by_ids: {missing} chunk(s) not found.")
        return res_dict

    async def delete_chunks_by_doc(self, doc_id: int) -> int:
        """
        Delete all child chunks belonging to a document.
        Returns the number of deleted rows.
        """
        async with self.get_session() as session:
            try:
                # Use selectinload to preload chunks to avoid lazy loading errors in asynchronous environments.
                stmt = select(Document).where(Document.id == doc_id).options(selectinload(Document.chunks))
                result = await session.execute(stmt)
                doc = result.scalar_one_or_none()
                
                if not doc:
                    logger.warning(f"[DB] delete_chunks_by_doc: Document {doc_id} not found.")
                    return 0

                count = len(doc.chunks)
                for chunk in doc.chunks:
                    await session.delete(chunk)
                await session.flush()
                
                logger.debug(f"[DB] Deleted {count} chunk(s) for doc_id={doc_id}.")
                return count

            except SQLAlchemyError:
                raise
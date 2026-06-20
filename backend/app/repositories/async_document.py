#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: Asynchronous Document Database Management

from datetime import datetime
from typing import List, Optional, Dict

from sqlalchemy import Tuple, delete, func, select, update

from app.infra.db.async_base import AsyncBaseDatabase
from app.infra.db.database import Document

class AsyncDocumentDatabase(AsyncBaseDatabase):
    """Asynchronous Document Table Operation Class"""

    # =========================================================================
    # Queries (Asynchronous)
    # =========================================================================

    async def get_doc(self, doc_id: int) -> Optional[Document]:
        async with self.get_session() as session:
            return await session.get(Document, doc_id)

    async def find_by_filename(self, kb_id: int, filename: str) -> Optional[Document]:
        async with self.get_session() as session:
            stmt = select(Document).where(
                Document.kb_id == kb_id,
                Document.filename == filename,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def find_by_hash(self, kb_id: int, hash_value: str) -> Optional[Document]:
        async with self.get_session() as session:
            stmt = select(Document).where(
                Document.kb_id == kb_id,
                Document.hash_value == hash_value,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_docs(
        self,
        kb_id: int,
        status_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Document], int]:
        """List documents for a knowledge base with optional status filter."""
        async with self.get_session() as session:
            query = select(Document).where(Document.kb_id == kb_id)
            
            if status_filter:
                query = query.where(Document.status == status_filter)

            # Total count
            count_query = select(func.count()).select_from(query.subquery())
            total: int = (await session.execute(count_query)).scalar_one()

            # Paginated results
            offset = (page - 1) * page_size
            rows = (
                await session.execute(
                    query.order_by(Document.created_at.desc())
                    .offset(offset)
                    .limit(page_size)
                )
            ).scalars().all()

            return list(rows), 

    async def get_chunk_ids_by_doc(self, doc_id: int) -> List[int]:
        """Get all chunk IDs associated with a document."""
        async with self.get_session() as session:
            result = await session.execute(
                select("chunk.id").select_from(Document.__table__.join("chunk"))
                .where(Document.id == doc_id)
            )
            return [row[0] for row in result.fetchall()]

    # =========================================================================
    # Writes (Asynchronous)
    # =========================================================================

    async def create_doc(self, **kwargs) -> Document:
        """Create a new document."""
        async with self.get_session() as session:
            doc = Document(**kwargs)
            session.add(doc)
            await session.flush()  # Get the ID before commit
            return doc

    async def mark_status(self, doc_id: int, status: str, error_message: Optional[str] = None) -> int:
        """Mark document status."""
        async with self.get_session() as session:
            values = {
                "status": status,
                "updated_at": datetime.now()
            }
            if error_message is not None:
                values["error_message"] = error_message
            
            result = await session.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(**values)
            )
            return result.rowcount

    async def update_hash(self, doc_id: int, hash_value: str, file_uri: str) -> int:
        """Update document hash and file URI."""
        async with self.get_session() as session:
            result = await session.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(
                    hash_value=hash_value,
                    file_uri=file_uri,
                    updated_at=datetime.now()
                )
            )
            return result.rowcount

    async def update_metadata(self, doc_id: int, metadata: dict) -> int:
        """Update document metadata."""
        async with self.get_session() as session:
            result = await session.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(
                    meta_data_json=metadata,
                    updated_at=datetime.now()
                )
            )
            return result.rowcount

    async def update_page_count(self, doc_id: int, page_count: int) -> int:
        """Update document page count."""
        async with self.get_session() as session:
            result = await session.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(
                    page_count=page_count,
                    updated_at=datetime.now()
                )
            )
            return result.rowcount

    async def update_chunk_count(self, doc_id: int, chunk_count: int) -> int:
        """Update document chunk count."""
        async with self.get_session() as session:
            result = await session.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(
                    chunk_count=chunk_count,
                    updated_at=datetime.now()
                )
            )
            return result.rowcount

    async def delete_doc(self, doc_id: int) -> int:
        """Delete a document."""
        async with self.get_session() as session:
            result = await session.execute(
                delete(Document).where(Document.id == doc_id)
            )
            return result.rowcount
    
    async def clear_error_message(self, doc_id: int) -> int:
        """Clear document error message."""
        async with self.get_session() as session:
            result = await session.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(
                    error_message=None,
                    updated_at=datetime.now()
                )
            )
            return result.rowcount

    async def get_citation_info_by_ids(self, doc_ids: List[int]) -> Dict[int, dict]:
        async with self.get_session() as session:
            stmt = select(Document.id, Document.filename, Document.meta_data_json).where(
                Document.id.in_(doc_ids)
            )
            result = await session.execute(stmt)
            rows = result.all()
        return {
            row[0]: {
                "filename":   row[1],
                **(row[2] or {}),
            }
            for row in rows
        }
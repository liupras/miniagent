#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: Asynchronous Document Database Management

import hashlib
import os
from datetime import datetime
from typing import List, Optional, Dict

from loguru import logger
from sqlalchemy import select

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
    ) -> List[Document]:
        async with self.get_session() as session:
            q = select(Document).where(Document.kb_id == kb_id)
            if status_filter:
                q = q.where(Document.status == status_filter)
            result = await session.execute(q)
            return list(result.scalars().all())

    # =========================================================================
    # Writes (Asynchronous)
    # =========================================================================

    async def create_doc(
        self,
        kb_id: int,
        hash_value: str,
        filename: str,
        mime_type: str,
        file_uri: str,
        file_size: int = 0,
        storage_type: str = "local",
        metadata: Optional[dict] = None,
    ) -> Document:
        """
        Insert a new document record with the status 'processing'.
        """
        async with self.get_session() as session:
            doc = Document(
                kb_id=kb_id,
                hash_value=hash_value,
                filename=filename,
                mime_type=mime_type,
                file_size=file_size,
                file_uri=file_uri,
                storage_type=storage_type,
                meta_data_json=metadata or {},
                status="processing",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            session.add(doc)
            # In an asynchronous environment, await and flush must be used.
            await session.flush()
            # A refresh is required to retrieve the auto-incrementing ID before the session is closed.
            await session.refresh(doc)
            logger.debug(f"[DB] Created Document id={doc.id} filename={filename}")
            return doc

    async def mark_status(
        self,
        doc_id: int,
        status: str,
        error_message: Optional[str] = None,        
    ) -> None:
        async with self.get_session() as session:
            doc = await session.get(Document, doc_id)
            if not doc:
                return
            doc.status     = status
            doc.updated_at = datetime.now()
            if error_message is not None:
                doc.error_message = error_message[:1000]            
        logger.debug(f"[DB] Document id={doc_id} → status={status}")

    async def update_hash(self, doc_id: int, hash_value: str, file_uri: str) -> None:
        async with self.get_session() as session:
            doc = await session.get(Document, doc_id)
            if doc:
                doc.hash_value = hash_value
                doc.file_uri   = file_uri
                doc.updated_at = datetime.now()

    async def update_metadata(self, doc_id: int, metadata: dict) -> None:
        async with self.get_session() as session:
            doc = await session.get(Document, doc_id)
            if doc:
                doc.meta_data_json = metadata
                doc.updated_at     = datetime.now()

    async def update_page_count(self, doc_id: int, page_count: int) -> None:
        async with self.get_session() as session:
            doc = await session.get(Document, doc_id)
            if doc:
                doc.page_count = page_count
                doc.updated_at = datetime.now()

    async def update_chunk_count(self, doc_id: int, chunk_count: int) -> None:
        async with self.get_session() as session:
            doc = await session.get(Document, doc_id)
            if doc:
                doc.chunk_count = chunk_count
                doc.updated_at  = datetime.now()

    async def delete_doc(self, doc_id: int) -> bool:
        async with self.get_session() as session:
            doc = await session.get(Document, doc_id)
            if not doc:
                return False
            await session.delete(doc)
        logger.debug(f"[DB] Deleted Document id={doc_id}")
        return True
    
    async def clear_error_message(self, doc_id: int) -> None:
        """Clear error_message for the specified document."""
        async with self.get_session() as session:
            doc = await session.get(Document, doc_id)
            if doc:
                doc.error_message = None
                doc.updated_at = datetime.now()
        logger.debug(f"[DB] Cleared error_message for Document id={doc_id}")

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

    # =========================================================================
    # Static helper (Maintain synchronization because it does not involve DB I/O.)
    # =========================================================================

    @staticmethod
    def hash_source(source: str) -> str:
        """
        Calculate the hash. Note: If the file is very large, reading the file will still be blocking I/O.
        For extremely high performance requirements, aiofiles can be used, but usually, keeping it synchronous is sufficient here.
        """
        if os.path.exists(source):
            h = hashlib.sha256()
            with open(source, "rb") as f:
                for block in iter(lambda: f.read(65536), b""):
                    h.update(block)
            return h.hexdigest()
        return hashlib.sha256(source.encode()).hexdigest()
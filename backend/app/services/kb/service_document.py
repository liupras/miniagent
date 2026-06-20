#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-27
# @description: Knowledge-base document service — pure orchestration.

import asyncio
from typing import List, Optional
from langchain_core.documents import Document as LC_Document

from loguru import logger
from sqlalchemy import Tuple

from app.utils.hash import sha256_hash

from .smart_document_loader import SmartDocumentLoader
from .small_to_big_base import ChunkConfig
from app.infra.retrieval.vector_store import VectorStoreManager
from app.runtime.task.progress_tracker import DocumentStatus,emitter
from app.infra.db.database import Document

class KBDocumentService:
    """
    Orchestrates add / update / delete of documents.
    """

    def __init__(
        self,
        container
    ):
        from app.core.service_container import ServiceContainer
        if not isinstance(container, ServiceContainer):
            raise TypeError(f"Expected ServiceContainer, got {type(container)}")
        
        from app.infra.search.bm25_manager import bm25_manager
        self.kb_db           = container.kb_db
        self.doc_db          = container.doc_db
        self.pc_db           = container.pc_db
        self.chunk_db        = container.chunk_db
        self.vector_registry = container.vector_registry
        self.bm25            = bm25_manager
        self.domain_registry = container.domain_registry
        self.domain_db = container.domain_db

        from app.storage.manager import storage
        self.storage = storage

    async def _get_vs(self, kb_id: int) -> VectorStoreManager:
        """
        Resolve the VectorStoreManager for *kb_id* from the registry.

        The registry caches managers after first creation, so this is cheap
        on all subsequent calls for the same KB.
        """
        return await self.vector_registry.get(kb_id)

    # =========================================================================
    # Public API
    # =========================================================================

    async def kb_exists(self,kb_id:int)->bool:
        return self.kb_db.kb_exists(kb_id=kb_id)

    async def list_docs(
        self,
        kb_id: int,
        status_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[int, List[Document]]:
        """List documents for a knowledge base."""
        items, total = await self.doc_db.list_docs(
            kb_id=kb_id,
            status_filter=status_filter,
            page=page,
            page_size=page_size
        )
        return total, items
    
    async def get_doc(self, doc_id: int) -> Optional[Document]:
        """Get a single document by ID."""
        doc = await self.doc_db.get_doc(doc_id)
        if doc is None:
            return None
        return doc
    
    async def add_document(
        self,
        kb_id:        int,
        source:       str,
        filename:     str,
        mime_type:    str,
        task_id:      str,
        file_size:    int            = 0,
        storage_type: str            = "local",
        metadata:     Optional[dict] = None,
    ):
        """
        Add a new document.
        • Same hash + completed  → skip (document-level dedup).
        • Same hash + processing/failed → clean up partial data, then retry.
        Since the document and chunk sizes will not be very large, hash collisions will not be considered.
        """
        E = emitter(task_id)
        await E("init", "🔍 Checking by hash …", 0)
        
        doc_hash = sha256_hash(source)
        existing = await self.doc_db.find_by_hash(kb_id, doc_hash)

        # ── Dedup ─────────────────────────────────────────────────────────
        if existing:
            if existing.status == DocumentStatus.COMPLETED.value:
                await E("done", f"⏭️  Duplicate — already indexed (id={existing.id}).", 100, done=True)
                return existing
            else:
                # ── Clean up stale interrupted record ────────────────────
                await E("init", "♻️  Cleaning up previous incomplete attempt …", 2)
                await self._cleanup_doc_data(existing.id, existing.kb_id, task_id)
                # ── Reset Document row ────────────────────────────────────
                await self.doc_db.mark_status(existing.id, DocumentStatus.PROCESSING.value, error_message="")
                doc = await self.doc_db.get_doc(existing.id)
                target_file_uri = f"kb_{kb_id}/{filename}"
                await asyncio.to_thread(self._add_storage_file, source, target_file_uri)
                await E("init", "document is saved.", 5)
        else:
            new_doc = Document(
                kb_id=kb_id,
                hash_value=doc_hash,
                filename=filename,
                mime_type=mime_type,
                file_uri=source,
                file_size=file_size,
                storage_type=storage_type,
                meta_data_json=metadata
            )
            data = new_doc.model_dump()
            doc = await self.doc_db.create_doc(**data)

        try:
            await self._process_document(doc.id, doc.kb_id, source, task_id)
            await self.doc_db.mark_status(doc.id, DocumentStatus.COMPLETED.value)
            await E("done", f"✅ Document (id={doc.id}) indexed successfully.", 100, done=True)
        except Exception as exc:
            logger.exception(f"[KB] add_document failed doc_id={doc.id}: {exc}")
            await self.doc_db.mark_status(doc.id, DocumentStatus.FAILED.value, error_message=str(exc))
            await E("error", f"❌ {exc}", 0, done=True, error=True)
            raise

        return await self.doc_db.get_doc(doc.id)

    async def update_document(
        self,
        doc_id:   int,
        source:   str,
        task_id:  str,
        metadata: Optional[dict] = None,
    ):
        """
        Replace document content.
        • Same hash + completed → only update metadata (no re-embedding).
        • Different hash → full cleanup + re-index.
        """
        E = emitter(task_id)
        await E("init", "🔍 Loading document record …", 0)

        doc = await self.doc_db.get_doc(doc_id)
        if not doc:
            await E("error", f"Document {doc_id} not found.", 0, done=True, error=True)
            raise ValueError(f"Document {doc_id} not found")

        new_hash = sha256_hash(source)

        # ── Content unchanged ─────────────────────────────────────────────
        if new_hash == doc.hash_value and doc.status == DocumentStatus.COMPLETED.value:
            if metadata:
                await self.doc_db.update_metadata(doc_id, metadata)
            await E("done", "⏭️  Content unchanged — only metadata updated.", 100, done=True)
            return await self.doc_db.get_doc(doc_id)

        # ── Full re-index ─────────────────────────────────────────────────
        await E("init", "♻️  Removing old vectors and index entries …", 5)
        await self._cleanup_doc_data(doc_id, doc.kb_id, task_id)

        # ── Delete old file from storage if URI has changed ───────────────
        if doc.file_uri and doc.file_uri != source:
            await E("init", "🗑️  Removing old file from storage …", 8)
            await asyncio.to_thread(self._delete_storage_file, doc.file_uri)

        await self.doc_db.update_hash(doc_id, new_hash, source)
        if metadata:
            await self.doc_db.update_metadata(doc_id, metadata)
        await self.doc_db.mark_status(doc_id, DocumentStatus.PROCESSING.value)

        try:
            await self._process_document(doc_id, doc.kb_id, source, task_id)
            await self.doc_db.mark_status(doc_id, DocumentStatus.COMPLETED.value)
            await self.doc_db.clear_error_message(doc_id)
            await E("done", f"✅ Document (id={doc_id}) updated.", 100, done=True)
        except Exception as exc:
            logger.exception(f"[KB] update_document failed doc_id={doc_id}: {exc}")
            await self.doc_db.mark_status(doc_id, DocumentStatus.FAILED.value, error_message=str(exc))
            await E("error", f"❌ {exc}", 0, done=True, error=True)
            raise

        return await self.doc_db.get_doc(doc_id)

    async def delete_document(self, doc_id: int, task_id: str) -> bool:
        """Delete document row plus all vectors and BM25 entries."""
        E = emitter(task_id)
        await E("init", "🔍 Loading document record …", 0)

        doc = await self.doc_db.get_doc(doc_id)
        if not doc:
            await E("error", f"Document {doc_id} not found.", 0, done=True, error=True)
            raise ValueError(f"Document {doc_id} not found")

        try:
            await self._cleanup_doc_data(doc_id, doc.kb_id, task_id)
            # ── Delete physical file from storage ─────────────────────────
            if doc.file_uri:
                await E("cleanup", "🗑️  Removing file from storage …", 8)
                await asyncio.to_thread(self._delete_storage_file, doc.file_uri)
            await self.doc_db.delete_doc(doc_id)
            await E("done", f"✅ Document (id={doc_id}) deleted.", 100, done=True)
            return True
        except Exception as exc:
            logger.exception(f"[KB] delete_document failed doc_id={doc_id}: {exc}")
            await E("error", f"❌ {exc}", 0, done=True, error=True)
            raise

    # =========================================================================
    # Internal pipeline
    # =========================================================================

    async def _process_document(
        self, doc_id: int, kb_id: int, source: str, task_id: str
    ) -> None:
        """
        Full indexing pipeline (progress 10 → 92%):
          load → split
          → child dedup → orphan-parent prune → parent dedup
          → save SQLite (flush) → ChromaDB → SQLite commit → BM25
        """
        loop = asyncio.get_running_loop()
        def on_batch(done: int, total: int) -> None:
            pct = 55 + 32 * done / total
            asyncio.run_coroutine_threadsafe(
                E("embed", f"🔢 Embedded {done}/{total} chunks …", pct),
                loop,
            )

        E  = emitter(task_id)
        vs = await self._get_vs(kb_id)

        # 1. Load ─────────────────────────────────────────────────────────
        await E("load", "📂 Loading document …", 10)
        loader   = SmartDocumentLoader(source)
        raw_docs = await asyncio.to_thread(loader.load)
        self._clean_meta(raw_docs)
        await self.doc_db.update_page_count(doc_id, len(raw_docs))
        await E("load", f"📄 Loaded {len(raw_docs)} page(s).", 20)

        # 2. Split ────────────────────────────────────────────────────────
        await E("split", "✂️  Splitting into chunks …", 25)
        kb = await self.kb_db.get_kb(kb_id) 
        domain = await self.domain_db.get_domain_by_kb_id(kb_id)       
        plugin    = self.domain_registry.get(domain.name)
        chunk_config = ChunkConfig(parent_chunk_size=kb.parent_size,
                                   parent_overlap=kb.parent_overlap,
                                   child_chunk_size=kb.chunk_size,
                                   child_overlap=kb.chunk_overlap)
        parent_chunks, small_chunks = await asyncio.to_thread(plugin.processor.process,raw_docs,kb_id,doc_id, chunk_config)
        await E("split", f"🔢 {len(parent_chunks)} parent / {len(small_chunks)} child chunks.", 35)

        # 3. Child-chunk dedup ────────────────────────────────────────────
        await E("dedup", "🔎 Deduplicating child chunks …", 37)
        small_chunks = await self.chunk_db.filter_new_chunks(kb_id, small_chunks)
        await E("dedup", f"✅ {len(small_chunks)} unique child chunks remain.", 40)
        if not small_chunks:
            raise ValueError(f"No small chunks...")

        # 4. Orphan-parent pruning ────────────────────────────────────────
        #    Drop parents whose every child was deduped away.
        surviving_indexes = {
            sc._extra_metadata.get("parent_index", 0) for sc in small_chunks
        }
        parent_chunks = [pc for pc in parent_chunks if pc.chunk_index in surviving_indexes]
        await E("dedup", f"✅ {len(parent_chunks)} parent chunks after orphan pruning.", 42)

        # 5. Parent-chunk dedup ───────────────────────────────────────────
        await E("dedup", "🔎 Deduplicating parent chunks …", 44)
        new_parents, existing_index_to_id = await self.pc_db.filter_new_parent_chunks(
            kb_id, parent_chunks
        )
        await E(
            "dedup",
            f"✅ {len(new_parents)} new / {len(existing_index_to_id)} already-stored parents.",
            46,
        )

        # 6. Save parent chunks (flush, no commit) ────────────────────────
        await E("db", "💾 Saving new parent chunks …", 48)
        await self.pc_db.save_parent_chunks(new_parents)

        # Build complete parent_index → db_id map
        parent_index_to_id: dict[int, int] = {
            **existing_index_to_id,
            **{pc.chunk_index: pc.id for pc in new_parents},
        }

        # 7. Save child chunks (flush, no commit) ─────────────────────────
        await E("db", "💾 Saving child chunks …", 51)
        await self.chunk_db.save_chunks(small_chunks, parent_index_to_id)

        # 8. ChromaDB vectors ─────────────────────────────────────────────
        await E("embed", "🧠 Embedding and storing vectors …", 55)      

        for sc in small_chunks:
            if "parent_index" in sc._extra_metadata:
                pidx = sc._extra_metadata.get("parent_index", 0)
                sc._extra_metadata["parent_id"] = parent_index_to_id[pidx]
                sc._extra_metadata.pop("parent_index", None)

        await asyncio.to_thread(vs.add_chunks, kb_id, small_chunks, 32, on_batch)
        await E("embed", f"✅ {len(small_chunks)} vectors stored in ChromaDB.", 87)

        # 9. Final commit (chunks now durably in SQLite) ───────────────────
        await self.doc_db.update_chunk_count(doc_id, len(small_chunks))
        await E("db", f"💾 {len(small_chunks)} chunks committed to SQLite.", 88)

        # 10. BM25 index ──────────────────────────────────────────────────
        await E("bm25", "📊 Updating BM25 index …", 89)
        bm25_docs = [
            {
                "chunk_id": str(sc.id),
                "text": sc.text,
                "_extra_metadata": {
                    **sc._extra_metadata,  # Retain all original metadata
                    "doc_id": sc.doc_id    # Added doc_id field
                }
            }
            for sc in small_chunks
        ]
        await asyncio.to_thread(self.bm25.add_documents, str(kb_id), bm25_docs)
        await E("bm25", "✅ BM25 index updated.", 92)

    def _delete_storage_file(self, file_uri: str) -> None:
        """
        Delete the physical file from the storage backend.
        Errors are logged but not re-raised to avoid blocking document cleanup.
        """
        try:
            self.storage.delete(file_uri)
            logger.debug(f"[Storage] Deleted file: {file_uri}")
        except Exception as exc:
            logger.warning(f"[Storage] Failed to delete file {file_uri}: {exc}")

    def _add_storage_file(self, source_path: str,target_path: str) -> str:
        """
        Add a file to the storage backend and return its URI.
        """
        try:
            with open(source_path, "rb") as f:
                file_uri = self.storage.save_file(
                    path=target_path, 
                    file_obj=f, 
                    overwrite=True
                )
            logger.debug(f"[Storage] Added file: {file_uri}")
            return file_uri
        except Exception as exc:
            logger.error(f"[Storage] Failed to add file {source_path}: {exc}")
            raise

    def _clean_meta(self,documents:list[LC_Document]):
        for doc in documents:
            if doc.metadata:
                doc.metadata.pop("source",None)
                doc.metadata.pop("original_encoding",None)

    async def _cleanup_doc_data(
        self, doc_id: int, kb_id: int, task_id: str
    ) -> None:
        """
        Remove all derived data (ChromaDB vectors, BM25 entries, SQLite chunks).
        Does NOT delete the Document row itself — caller decides.
        """
        E  = emitter(task_id)
        vs = await self._get_vs(kb_id)

        chunk_ids = await self.chunk_db.get_chunk_ids_by_doc(doc_id)

        await E("cleanup", "🗑️  Removing ChromaDB vectors …", 3)
        await asyncio.to_thread(vs.delete_by_doc_id, kb_id, doc_id)

        await E("cleanup", "🗑️  Removing BM25 entries …", 5)
        await asyncio.to_thread(
            self.bm25.delete_documents, str(kb_id), [str(i) for i in chunk_ids]
        )

        await E("cleanup", "🗑️  Removing SQLite chunk records …", 7)
        await self.chunk_db.delete_chunks_by_doc(doc_id=doc_id)
        await self.pc_db.delete_by_doc(doc_id)

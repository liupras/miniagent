#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-27
# @description: FastAPI router — knowledge-base document CRUD with SSE progress.

import os
import asyncio
import json
import tempfile
import uuid
from typing import Optional

from fastapi import (
    Request,
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.kb.service_document import KBDocumentService, ProgressTracker
from app.services.kb.service_smart_router import KBSmartRouterService

# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────
router = APIRouter()

# ─────────────────────────────────────────────────────────────────
# Dependencies
# ─────────────────────────────────────────────────────────────────

from app.core.service_container import ServiceContainer

def get_container(request: Request) -> ServiceContainer:
    return request.app.state.container

def get_service_document(
    container: ServiceContainer = Depends(get_container),
) -> KBDocumentService:
    """
    Return the long-lived KBDocumentService singleton from ServiceContainer.

    The service holds a VectorStoreRegistry and resolves the correct
    VectorStoreManager per kb_id at call time.  kb_id is passed per-call,
    not at construction time.
    """
    return container.document_service

def get_service_smart_router(
    container: ServiceContainer = Depends(get_container),
) -> KBSmartRouterService:
    """
    Return the long-lived KBSmartRouterService singleton from ServiceContainer.

    The service delegates to SmartRouterFactory, which caches one SmartRouter
    per router_config_id.  Must be a singleton — never recreate per request.

    Call container.smart_router_service.invalidate(router_config_id) after
    updating a RouterConfig in the DB.
    """
    return container.smart_router_service

# ─────────────────────────────────────────────────────────────────
# Response Models
# ─────────────────────────────────────────────────────────────────
class TaskCreatedResponse(BaseModel):
    task_id: str
    message: str

# ─────────────────────────────────────────────────────────────────────────────
# SSE — real-time progress stream
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/tasks/{task_id}/progress",
    summary="SSE — real-time task progress"
)
async def task_progress(task_id: str):
    """
    Server-Sent Events stream.  Connect and receive JSON events until
    `done=true` or `error=true`.

    **Event shape**
    ```json
    {
      "stage":    "embed",
      "message":  "🧠 Embedding 64/128 chunks …",
      "progress": 72.5,
      "done":     false,
      "error":    false,
      "ts":       "2026-02-27T10:00:00.000000"
    }
    ```
    """
    queue = ProgressTracker.get(task_id)
    if queue is None:
        raise HTTPException(404, "Task not found or already finished.")

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("done") or event.get("error"):
                    break
        finally:
            ProgressTracker.remove(task_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Add document — file upload
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/{kb_id}/documents",
    response_model=TaskCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a file document to a knowledge base"
)
async def add_document(
    kb_id:            int,
    background_tasks: BackgroundTasks,
    file:             UploadFile            = File(...),
    metadata:         Optional[str]         = Form(None),
    container:        ServiceContainer      = Depends(get_container),
    service:          KBDocumentService     = Depends(get_service_document),
):
    if not container.kb_db.kb_exists(kb_id):
        raise HTTPException(404, f"KnowledgeBase {kb_id} not found.")

    suffix  = os.path.splitext(file.filename)[1]
    content = await file.read()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(content)
        tmp.flush()
        tmp_path = tmp.name
    finally:
        tmp.close()

    meta    = json.loads(metadata) if metadata else {}
    task_id = str(uuid.uuid4())
    ProgressTracker.create(task_id)

    async def run():
        try:
            await service.add_document(
                kb_id     = kb_id,
                source    = tmp_path,
                filename  = file.filename,
                mime_type = suffix.lstrip(".").lower(),
                task_id   = task_id,
                file_size = len(content),
                metadata  = meta,
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    background_tasks.add_task(run)
    return TaskCreatedResponse(
        task_id = task_id,
        message = "Document upload started. Stream progress via SSE.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Add document — URL
# ─────────────────────────────────────────────────────────────────────────────
class AddUrlRequest(BaseModel):
    url:      str
    metadata: Optional[dict] = None


@router.post(
    "/{kb_id}/documents/url",
    response_model=TaskCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Import a document from URL"
)
async def add_document_url(
    kb_id:            int,
    body:             AddUrlRequest,
    background_tasks: BackgroundTasks,
    container:        ServiceContainer  = Depends(get_container),
    service:          KBDocumentService = Depends(get_service_document),
):
    if not container.kb_db.kb_exists(kb_id):
        raise HTTPException(404, f"KnowledgeBase {kb_id} not found.")

    task_id = str(uuid.uuid4())
    ProgressTracker.create(task_id)

    background_tasks.add_task(
        service.add_document,
        kb_id     = kb_id,
        source    = body.url,
        filename  = body.url.split("/")[-1] or body.url,
        mime_type = "url",
        task_id   = task_id,
        metadata  = body.metadata or {},
    )
    return TaskCreatedResponse(
        task_id = task_id,
        message = "URL import started. Stream progress via SSE.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Update document — re-upload file
# ─────────────────────────────────────────────────────────────────────────────
@router.put(
    "/{kb_id}/documents/{doc_id}",
    response_model=TaskCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Replace document content (file upload)"
)
async def update_document(
    kb_id:            int,
    doc_id:           int,
    background_tasks: BackgroundTasks,
    file:             UploadFile            = File(...),
    metadata:         Optional[str]         = Form(None),
    container:        ServiceContainer      = Depends(get_container),
    service:          KBDocumentService     = Depends(get_service_document),
):
    """If file hash is unchanged only metadata is updated (no re-embedding)."""
    doc = await container.doc_db.get_doc(doc_id)
    if not doc or doc.kb_id != kb_id:
        raise HTTPException(404, f"Document {doc_id} not found in KB {kb_id}.")

    suffix  = os.path.splitext(file.filename)[1]
    content = await file.read()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(content)
        tmp.flush()
        tmp_path = tmp.name
    finally:
        tmp.close()

    meta    = json.loads(metadata) if metadata else None
    task_id = str(uuid.uuid4())
    ProgressTracker.create(task_id)

    async def run():
        try:
            await service.update_document(
                doc_id  = doc_id,
                source  = tmp_path,
                task_id = task_id,
                metadata = meta,
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    background_tasks.add_task(run)
    return TaskCreatedResponse(
        task_id = task_id,
        message = "Document update started. Stream progress via SSE.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Delete document
# ─────────────────────────────────────────────────────────────────────────────
@router.delete(
    "/{kb_id}/documents/{doc_id}",
    response_model=TaskCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Delete a document from knowledge base"
)
async def delete_document(
    kb_id:     int,
    doc_id:    int,
    background_tasks: BackgroundTasks,
    container: ServiceContainer  = Depends(get_container),
    service:   KBDocumentService = Depends(get_service_document),
):
    doc = await container.doc_db.get_doc(doc_id)
    if not doc or doc.kb_id != kb_id:
        raise HTTPException(404, f"Document {doc_id} not found in KB {kb_id}.")

    task_id = str(uuid.uuid4())
    ProgressTracker.create(task_id)
    background_tasks.add_task(service.delete_document, doc_id, task_id)
    return TaskCreatedResponse(
        task_id = task_id,
        message = "Document deletion started. Stream progress via SSE.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Retry failed document
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/{kb_id}/documents/{doc_id}/retry",
    response_model=TaskCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry a failed or stuck document"
)
async def retry_document(
    kb_id:     int,
    doc_id:    int,
    background_tasks: BackgroundTasks,
    container: ServiceContainer  = Depends(get_container),
    service:   KBDocumentService = Depends(get_service_document),
):
    doc = await container.doc_db.get_doc(doc_id)
    if not doc or doc.kb_id != kb_id:
        raise HTTPException(404, f"Document {doc_id} not found in KB {kb_id}.")
    if doc.status == "completed":
        raise HTTPException(400, "Document already completed. Use PUT to update content.")
    if not doc.file_path:
        raise HTTPException(400, "No stored file path — cannot retry.")

    task_id = str(uuid.uuid4())
    ProgressTracker.create(task_id)
    background_tasks.add_task(
        service.add_document,
        kb_id     = kb_id,
        source    = doc.file_path,
        filename  = doc.filename,
        file_type = doc.file_type,
        task_id   = task_id,
        file_size = doc.file_size or 0,
        metadata  = doc.meta_data_json or {},
    )
    return TaskCreatedResponse(
        task_id = task_id,
        message = "Document retry started. Stream progress via SSE.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# List documents
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/{kb_id}/documents",
    summary="List all documents in a knowledge base"
)
async def list_documents(
    kb_id:         int,
    status_filter: Optional[str]   = None,
    container:     ServiceContainer = Depends(get_container),
):
    if not container.kb_db.kb_exists(kb_id):
        raise HTTPException(404, f"KnowledgeBase {kb_id} not found.")
    docs = await container.doc_db.list_docs(kb_id, status_filter)
    return [_doc_to_dict(d) for d in docs]


# ─────────────────────────────────────────────────────────────────────────────
# Get document detail
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/{kb_id}/documents/{doc_id}",
    summary="Get document detail"
)
async def get_document(
    kb_id:     int,
    doc_id:    int,
    container: ServiceContainer = Depends(get_container),
):
    doc = await container.doc_db.get_doc(doc_id)
    if not doc or doc.kb_id != kb_id:
        raise HTTPException(404, f"Document {doc_id} not found in KB {kb_id}.")
    return _doc_to_dict(doc, detail=True)

@router.post(
    "/smart-router/{router_config_id}/invalidate",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Invalidate cached SmartRouter for a RouterConfig"
)
async def invalidate_smart_router(
    router_config_id: str,
    service:          KBSmartRouterService = Depends(get_service_smart_router),
):
    """
    Evict the cached :class:`SmartRouter` instance for *router_config_id*.

    Call this endpoint after updating a RouterConfig in the database so that
    the next query rebuilds the router with the new settings.
    """
    service.invalidate(router_config_id)

# ─────────────────────────────────────────────────────────────────────────────
# Internal serialiser
# ─────────────────────────────────────────────────────────────────────────────
def _doc_to_dict(doc, detail: bool = False) -> dict:
    base = {
        "id":            doc.id,
        "kb_id":         doc.kb_id,
        "filename":      doc.filename,
        "file_type":     doc.file_type,
        "file_size":     doc.file_size,
        "status":        doc.status,
        "chunk_count":   doc.chunk_count,
        "hash_value":    doc.hash_value,
        "error_message": doc.error_message,
        "created_at":    doc.created_at.isoformat() if doc.created_at else None,
        "updated_at":    doc.updated_at.isoformat() if doc.updated_at else None,
    }
    if detail:
        base["page_count"] = doc.page_count
        base["meta_data"]  = doc.meta_data_json
    return base

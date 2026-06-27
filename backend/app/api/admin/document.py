#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-27
# @description: knowledge-base document CRUD with SSE progress.

import os
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
    UploadFile,
)

from app.schemas.common import ApiResponse
from app.core.security.auth_permission import AuthPermission
from app.runtime.task.progress_tracker import ProgressTracker
from app.schemas.admin.document import DocumentListOut, DocumentRead, TaskCreatedResponse
from app.services.kb.service_document import KBDocumentService

_list   = AuthPermission.Permission("document:list")
_add    = AuthPermission.Permission("document:add")
_edit   = AuthPermission.Permission("document:edit")
_delete = AuthPermission.Permission("document:delete")

# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────
router = APIRouter()

# ─────────────────────────────────────────────────────────────────
# Dependencies
# ─────────────────────────────────────────────────────────────────

def get_service(request: Request) -> KBDocumentService:
    """
    Return the long-lived KBDocumentService singleton from ServiceContainer.

    The service holds a VectorStoreRegistry and resolves the correct
    VectorStoreManager per kb_id at call time.  kb_id is passed per-call,
    not at construction time.
    """
    return request.app.state.container.document_service

# ─────────────────────────────────────────────────────────────────────────────
# List documents
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "",
    response_model=ApiResponse, 
    summary="List all documents in a knowledge base"
)
async def list_documents(
    kb_id:         Optional[int]   = None,
    status_filter: Optional[str]   = None,
    page: int = 1,
    page_size: int = 20,
    service:   KBDocumentService = Depends(get_service),
    caller_id:        int        = Depends(_list),
):    
    total, items = await service.list_docs(
        kb_id=kb_id,
        status_filter=status_filter,
        page=page,
        page_size=page_size
    )
    data = DocumentListOut(
        total=total, 
        page=page, 
        page_size=page_size, 
        items=[DocumentRead.model_validate(item) for item in items]
    )
    
    return ApiResponse(data=data)

@router.get(
    "/{kb_id}/{doc_id}",
    response_model=ApiResponse, 
    summary="Get document detail"
)
async def get_document(
    kb_id:     int,
    doc_id:    int,
    service:   KBDocumentService = Depends(get_service),
    caller_id:        int                   = Depends(_list),
):
    doc = await service.get_doc(doc_id)    
    data = DocumentRead.model_validate(doc)
    return ApiResponse(data=data)

# ─────────────────────────────────────────────────────────────────────────────
# Add document — file upload
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/{kb_id}",
    response_model=ApiResponse,    
    summary="Upload a file document to a knowledge base"
)
async def add_document(
    kb_id:            int,
    background_tasks: BackgroundTasks,
    file:             UploadFile            = File(...),
    metadata:         Optional[str]         = Form(None),
    service:          KBDocumentService     = Depends(get_service),
    caller_id:        int                   = Depends(_add),
):
    await service.check_exists(kb_id)
    
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
    data = TaskCreatedResponse(
        task_id = task_id,
        message = "Document upload started. Stream progress via SSE.",
    )
    return ApiResponse(data=data)

# ─────────────────────────────────────────────────────────────────────────────
# Update document — re-upload file
# ─────────────────────────────────────────────────────────────────────────────
@router.put(
    "/{kb_id}/{doc_id}",
    response_model=ApiResponse, 
    summary="Replace document content (file upload)"
)
async def update_document(
    kb_id:            int,
    doc_id:           int,
    background_tasks: BackgroundTasks,
    file:             UploadFile            = File(...),
    metadata:         Optional[str]         = Form(None),
    service:          KBDocumentService     = Depends(get_service),
    caller_id:        int                   = Depends(_edit),
):
    """If file hash is unchanged only metadata is updated (no re-embedding)."""
    await service.get_doc(doc_id)

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
                kb_id   = kb_id,
                doc_id  = doc_id,
                source  = tmp_path,
                filename= file.filename,
                task_id = task_id,
                metadata = meta,
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    background_tasks.add_task(run)
    data = TaskCreatedResponse(
        task_id = task_id,
        message = "Document update started. Stream progress via SSE.",
    )
    return ApiResponse(data=data)


# ─────────────────────────────────────────────────────────────────────────────
# Delete document
# ─────────────────────────────────────────────────────────────────────────────
@router.delete(
    "/{kb_id}/{doc_id}",
    response_model=ApiResponse, 
    summary="Delete a document from knowledge base"
)
async def delete_document(
    kb_id:     int,
    doc_id:    int,
    background_tasks: BackgroundTasks,    
    service:   KBDocumentService        = Depends(get_service),
    caller_id:        int               = Depends(_delete),
):
    await service.get_doc(doc_id)

    task_id = str(uuid.uuid4())
    ProgressTracker.create(task_id)
    background_tasks.add_task(service.delete_document, doc_id, task_id)
    data = TaskCreatedResponse(
        task_id = task_id,
        message = "Document deletion started. Stream progress via SSE.",
    )
    return ApiResponse(data=data)

@router.get(
    "/{kb_id}/{doc_id}/chunks",
    response_model=ApiResponse,
)
async def get_document_chunks(
    kb_id: int, 
    doc_id: int,
    page: int = 1,
    page_size: int = 20,
    service:   KBDocumentService        = Depends(get_service),
    caller_id:        int               = Depends(_list),
):
    result = await service.get_document_chunks(
        doc_id, page, page_size
    )
    return ApiResponse(data=result)

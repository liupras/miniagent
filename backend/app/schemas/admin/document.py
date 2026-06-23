#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-17
# @description: Pydantic schemas for Document CRUD

from __future__ import annotations

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class _DocumentBase(BaseModel):
    """Fields shared by Create / Update requests."""

    kb_id: int = Field(..., description="Knowledge base ID")
    hash_value: str = Field(..., max_length=64, description="Document hash value (SHA-256)")
    filename: str = Field(..., max_length=255, description="File name")
    mime_type: str = Field(..., max_length=50, description="File type")
    file_size: Optional[int] = Field(None, description="File size (bytes)")
    file_uri: Optional[str] = Field(None, max_length=1024, description="File storage URI (local path or cloud URL)")
    storage_type: str = Field(default="local", max_length=20, description="Storage type: local or cloud")
    chunk_count: int = Field(default=0, description="Number of blocks")
    meta_data_json: Optional[Dict[str, Any]] = Field(None, description="Metadata information, JSON format string")
    status: str = Field(default="pending", max_length=20, description="Processing status: pending, processing, completed, failed")
    error_message: Optional[str] = Field(None, description="Error message if processing failed")


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class DocumentCreate(_DocumentBase):
    """Body for POST /documents — all core fields are required."""

    kb_id: int = Field(..., description="Knowledge base ID")
    hash_value: str = Field(..., max_length=64, description="Document hash value (SHA-256)")
    filename: str = Field(..., max_length=255, description="File name")
    mime_type: str = Field(..., max_length=50, description="File type")


class DocumentUpdate(_DocumentBase):
    """Body for PATCH /documents/{id} — all fields optional (partial update)."""

    pass


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class DocumentRead(_DocumentBase):
    """Full document representation returned to the client."""

    id: int

    model_config = {"from_attributes": True}


class DocumentListOut(BaseModel):
    """Paginated list wrapper."""

    total: int
    page: int
    page_size: int
    items: list[DocumentRead]


# ---------------------------------------------------------------------------
# Additional schemas for API responses
# ---------------------------------------------------------------------------

class DocumentProgress(BaseModel):
    """Document processing progress information."""
    
    task_id: str
    status: str
    message: str
    progress: float
    done: bool
    error: Optional[str] = None

    model_config = {"from_attributes": True}

class TaskCreatedResponse(BaseModel):
    task_id: str
    message: str
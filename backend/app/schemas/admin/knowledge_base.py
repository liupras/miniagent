#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-13
# @description: Pydantic schemas for KnowledgeBase CRUD

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class _KnowledgeBaseBase(BaseModel):
    """Fields shared by Create / Update requests."""

    name: str = Field(..., max_length=100, description="Knowledge base name")    
    domain_id: int = Field(..., description="Domain this KB belongs to")
    keywords: Optional[list[str]] = Field(None, description="List of keywords for SmartRouter keyword matching")
    description: Optional[str] = Field(None, description="Knowledge base description")
    collection_name: str = Field(..., max_length=100, description="VectorDB collection name")
    embedding_id: Optional[int] = Field(None, description="Embedding configuration ID")
    chunk_size: int = Field(400, description="Block size (number of characters)")
    chunk_overlap: int = Field(80, description="Block overlap (number of characters)")
    parent_size: int = Field(1800, description="Parent block size (number of characters)")
    parent_overlap: int = Field(200, description="Parent block overlap (number of characters)")

    llm_id: Optional[int] = Field(None, description="LLM configuration ID")
    is_active: bool = Field(True, description="Activate or not?")

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class KnowledgeBaseCreate(_KnowledgeBaseBase):
    """Body for POST /knowledge_bases — all core fields are required."""

    name: str = Field(..., max_length=100, description="Knowledge base name")
    domain_id: int = Field(..., description="Domain this KB belongs to")
    collection_name: str = Field(..., max_length=100, description="VectorDB collection name")


class KnowledgeBaseUpdate(_KnowledgeBaseBase):
    """Body for PATCH /knowledge_bases/{id} — all fields optional (partial update)."""

    pass


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class KnowledgeBaseRead(_KnowledgeBaseBase):
    """Full knowledge base representation returned to the client."""

    id: int
    document_count: int = Field(0, description="Number of documents")
    chunk_count: int = Field(0, description="Number of blocks")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeBaseListOut(BaseModel):
    """Paginated list wrapper."""

    total: int
    page: int
    page_size: int
    items: list[KnowledgeBaseRead]


class KnowledgeBaseOption(BaseModel):
    """Knowledge base option for dropdown selection."""

    id: int
    name: str

    model_config = {"from_attributes": True}


class KnowledgeBaseStats(BaseModel):
    """Knowledge base statistics."""

    id: int
    name: str
    document_count: int
    chunk_count: int
    created_at: datetime
    updated_at: datetime
    is_active: bool
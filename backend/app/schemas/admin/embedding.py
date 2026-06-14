#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-14
# @description: Pydantic schemas for Embedding CRUD

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class _EmbeddingBase(BaseModel):
    """Fields shared by Create / Update requests."""

    name: str = Field(..., max_length=100, description="Embedding name")
    provider_name: str = Field(..., max_length=50, description="Embedding provider name, e.g., openai, local, etc.")
    base_url: str = Field(..., max_length=1024, description="Base URL for the embedding service")
    api_key: Optional[str] = Field(None, max_length=512, description="API key (optional for local models)")
    model_name: str = Field(..., max_length=100, description="Model name")
    max_tokens: int = Field(default=512, description="Maximum tokens")


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class EmbeddingCreate(_EmbeddingBase):
    """Body for POST /embeddings — all core fields are required."""

    name: str = Field(..., max_length=100, description="Embedding name")
    provider_name: str = Field(..., max_length=50, description="Embedding provider name, e.g., openai, local, etc.")
    base_url: str = Field(..., max_length=1024, description="Base URL for the embedding service")
    model_name: str = Field(..., max_length=100, description="Model name")
    max_tokens: int = Field(default=512, description="Maximum tokens")


class EmbeddingUpdate(_EmbeddingBase):
    """Body for PATCH /embeddings/{id} — all fields optional (partial update)."""

    pass


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class EmbeddingRead(_EmbeddingBase):
    """Full embedding representation returned to the client."""

    id: int

    model_config = {"from_attributes": True}


class EmbeddingListOut(BaseModel):
    """Paginated list wrapper."""

    total: int
    page: int
    page_size: int
    items: list[EmbeddingRead]


class EmbeddingOption(BaseModel):
    """Embedding option for dropdown selection."""

    id: int
    name: str

    model_config = {"from_attributes": True}
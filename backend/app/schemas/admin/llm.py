#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-30
# @description: LLM Pydantic Schemas

from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field, model_validator

class LLMBase(BaseModel):
    name: str = Field(..., max_length=100, description="LLM display name (unique)")
    provider_name: str = Field(..., max_length=50, description="Provider, e.g. openai / ollama")
    base_url: str = Field(..., max_length=1024, description="API base URL")
    api_key: Optional[str] = Field(None, max_length=512, description="API key (optional for local models)")
    model_name: str = Field(..., max_length=100, description="Model identifier")
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    context_window_tokens: int = Field(
        40000,
        ge=1,
        description="Maximum context window shared by input and output tokens",
    )
    max_output_tokens: int = Field(
        4096,
        ge=1,
        description="Default maximum output tokens for a single completion",
    )
    capabilities: Optional[Dict[str, Any]] = Field(None, description="Free-form capability flags")

    @model_validator(mode="after")
    def validate_token_limits(self):
        if self.max_output_tokens > self.context_window_tokens:
            raise ValueError("max_output_tokens must not exceed context_window_tokens")
        return self


class LLMCreate(LLMBase):
    pass


class LLMUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    provider_name: Optional[str] = Field(None, max_length=50)
    base_url: Optional[str] = Field(None, max_length=1024)
    api_key: Optional[str] = Field(None, max_length=512)
    model_name: Optional[str] = Field(None, max_length=100)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    context_window_tokens: Optional[int] = Field(None, ge=1)
    max_output_tokens: Optional[int] = Field(None, ge=1)
    capabilities: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_token_limits(self):
        if (
            self.context_window_tokens is not None
            and self.max_output_tokens is not None
            and self.max_output_tokens > self.context_window_tokens
        ):
            raise ValueError("max_output_tokens must not exceed context_window_tokens")
        return self


class LLMUpsert(LLMBase):
    """Used for create-or-update operations."""
    pass


class LLMOut(LLMBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class LLMOptionItem(BaseModel):
    """Lightweight projection used by dropdown selectors (e.g. Agent form)."""
    id: int
    name: str
    provider_name: str
    model_name: str

    model_config = {"from_attributes": True}


class LLMListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    provider_name: Optional[str] = None
    model_name: Optional[str] = None

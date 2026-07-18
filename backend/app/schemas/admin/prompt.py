#!/usr/bin/python
# -*- coding:utf-8 -*-

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.repositories.async_prompt import normalize_prompt_lang


class PromptIdentity(BaseModel):
    key: str = Field(..., min_length=1, max_length=200)
    lang: str = Field(..., min_length=2, max_length=10)

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Prompt key cannot be blank")
        return value

    @field_validator("lang")
    @classmethod
    def normalize_lang(cls, value: str) -> str:
        normalized = normalize_prompt_lang(value)
        parts = normalized.split("_", 1)
        if not parts[0].isalpha() or not 2 <= len(parts[0]) <= 3:
            raise ValueError("Invalid language tag")
        if len(parts) == 2 and (
            not parts[1].isalpha() or not 2 <= len(parts[1]) <= 4
        ):
            raise ValueError("Invalid language tag")
        return normalized


class PromptCreate(PromptIdentity):
    value: str
    description: Optional[str] = Field(None, max_length=255)


class PromptUpdate(BaseModel):
    value: str
    description: Optional[str] = Field(None, max_length=255)


class PromptBulkUpsertItem(PromptCreate):
    pass


class PromptBulkUpsert(BaseModel):
    items: list[PromptBulkUpsertItem] = Field(..., min_length=1, max_length=500)


class PromptBulkResult(BaseModel):
    created: int
    updated: int


class PromptOut(PromptCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

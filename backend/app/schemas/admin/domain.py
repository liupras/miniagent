#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-05
# @description: Pydantic schemas for Domain CRUD

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class _DomainBase(BaseModel):
    """Fields shared by Create / Update requests."""

    name: Optional[str] = Field(
        None,
        max_length=50,
        examples=["law_cn"],
        description="Domain identifier, e.g. company_law_cn / labor_contract_law_cn",
    )
    type: Optional[str] = Field(
        None,
        max_length=50,
        examples=["law"],
        description="Domain type, e.g. general / law / doctor",
    )
    processor_class: Optional[str] = Field(
        None,
        max_length=100,
        examples=["app.services.kb.law.LawSmallToBigProcessor"],
        description="Fully qualified processor class path",
    )
    plugin_class: Optional[str] = Field(
        None,
        max_length=100,
        examples=["app.services.kb.law.LawDomainPlugin"],
        description="Fully qualified plugin class path",
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable description shown in the UI",
    )
    metadata_schema: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "JSON Schema for domain-specific document metadata fields; "
            "drives the dynamic upload form in the UI"
        ),
    )

    @field_validator("name")
    @classmethod
    def name_no_spaces(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and " " in v:
            raise ValueError("Domain name must not contain spaces")
        return v

    '''
    @field_validator("processor_class", "plugin_class")
    @classmethod
    def dotted_path(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and "." not in v:
            raise ValueError("Class path must be a fully qualified dotted path")
        return v
    '''

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class DomainCreate(_DomainBase):
    """Body for POST /domains — all core fields are required."""

    name: str = Field(..., max_length=50, description="Unique domain identifier")
    type: str = Field(..., max_length=50, description="Domain type")
    processor_class: str = Field(..., max_length=100, description="Fully qualified processor class")
    plugin_class: str = Field(..., max_length=100, description="Fully qualified plugin class")


class DomainUpdate(_DomainBase):
    """Body for PATCH /domains/{id} — all fields optional (partial update)."""

    @model_validator(mode="after")
    def at_least_one_field(self) -> "DomainUpdate":
        provided = {
            k: v
            for k, v in self.model_dump().items()
            if v is not None
        }
        if not provided:
            raise ValueError("At least one field must be provided for update")
        return self


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class DomainRead(BaseModel):
    """Full domain representation returned to the client."""

    id: int
    name: str
    type: str
    processor_class: str
    plugin_class: str
    description: Optional[str]
    metadata_schema: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DomainListResponse(BaseModel):
    """Paginated list wrapper."""

    total: int
    page: int
    page_size: int
    items: list[DomainRead]
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-03
# @description: Tool Pydantic Schemas

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.i18n.i18n import t

VALID_TOOL_TYPES = {"function", "api", "smart_router", "sql_agent"}

ToolType = Literal["function", "api", "smart_router", "sql_agent"]


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class ToolBase(BaseModel):
    name: str = Field(..., max_length=100, description="Unique tool name")
    description: str | None = Field(None, description="Tool description")
    tool_type: ToolType = Field("function", description="Tool type")
    tool_schema: dict[str, Any] = Field(..., description="JSON Schema definition")
    config: dict[str, Any] | None = Field(None, description="Extra config (JSON)")
    is_active: bool = Field(True, description="Active?")

    @field_validator("tool_type")
    @classmethod
    def validate_tool_type(cls, v: str) -> str:
        if v not in VALID_TOOL_TYPES:
            raise ValueError(t("tool.tool_type_invalid", VALID_TOOL_TYPES=VALID_TOOL_TYPES))
        return v


# ---------------------------------------------------------------------------
# Create / Update
# ---------------------------------------------------------------------------

class ToolCreate(ToolBase):
    pass


class ToolUpdate(BaseModel):
    """All fields optional for partial update (PATCH semantics)."""
    name: str | None = Field(None, max_length=100)
    description: str | None = None
    tool_type: ToolType | None = None
    tool_schema: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None

    @field_validator("tool_type")
    @classmethod
    def validate_tool_type(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_TOOL_TYPES:
            raise ValueError(t("tool.tool_type_invalid", VALID_TOOL_TYPES=VALID_TOOL_TYPES))
        return v


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class ToolRead(ToolBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

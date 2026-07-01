#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-08
# @description: Router Config Pydantic Schemas

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, field_validator

from app.core.i18n.i18n import t

VALID_SELECTION_STRATEGIES = {"keyword", "embedding"}


class RouterConfigBase(BaseModel):
    selection_strategy: str = "embedding"
    fallback_to_all: bool = True
    max_kb_count: int = 3
    extra_config: Optional[dict[str, Any]] = None

    @field_validator("selection_strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        if v not in VALID_SELECTION_STRATEGIES:
            raise ValueError(
                f"selection_strategy must be one of {VALID_SELECTION_STRATEGIES}, got: {v!r}"
            )
        return v

    @field_validator("max_kb_count")
    @classmethod
    def validate_max_kb_count(cls, v: int) -> int:
        if v < 1:
            raise ValueError(t("router_config.max_kb_count"))
        return v


class RouterConfigUpdate(RouterConfigBase):
    selection_strategy: Optional[str] = None
    fallback_to_all: Optional[bool] = None
    max_kb_count: Optional[int] = None
    extra_config: Optional[dict[str, Any]] = None


class RouterConfigResponse(RouterConfigBase):
    config_id: str
    created_at: datetime

    model_config = {"from_attributes": True}
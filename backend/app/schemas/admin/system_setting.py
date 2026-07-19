#!/usr/bin/python
# -*- coding:utf-8 -*-

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


SettingValueType = Literal["string", "int", "float", "bool", "json"]


class SystemSettingUpdate(BaseModel):
    """Only the value of a predefined system setting may be changed."""

    value: str = Field(..., description="Setting value, stored as a string")


class SystemSettingOut(BaseModel):
    key: str
    value: str
    value_type: SettingValueType
    group: str
    description: Optional[str] = None
    is_readonly: bool
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

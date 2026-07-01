#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-01
# @description: Web Search Schemas

from litellm import Field
from pydantic import BaseModel


class CacheInfoResponse(BaseModel):
    """Per-tool result-cache statistics."""
    pipelines: dict = Field(description="Mapping of tool_name → cache stats dict (or null).")
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-29
# @description: Shared Pydantic schemas used across all modules

from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

# T can be any Pydantic output model (LLMOut, AgentOut, etc.).
T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    """
    Generic paginated result wrapper.

    Usage
    -----
    PageResult[LLMOut](total=100, page=1, page_size=20, data=[...])
    PageResult[AgentOut](total=50,  page=2, page_size=10, data=[...])
    """
    total: int = Field(..., description="Total number of records matching the query")
    page: int = Field(..., description="Current page number (1-based)")
    page_size: int = Field(..., description="Number of items per page")
    data: List[T] = Field(default_factory=list, description="Records on this page")


class ApiResponse(BaseModel, Generic[T]):
    """
    Generic top-level API response envelope.

    Usage
    -----
    ApiResponse[PageResult[LLMOut]](data=page_result)
    ApiResponse[AgentOut](data=agent_out)
    ApiResponse[None](message="Deleted successfully")   # no data
    """
    code: int = Field(200, description="Business status code, 200 = success")
    message: str = Field("success", description="Human-readable status message")
    data: Optional[T] = Field(None, description="Response payload")
    
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
    

class BaseDomainError(Exception):
    """Business Logic Exception Base Class"""
    def __init__(self, entity_name: str, entity_id: Any, message: str):
        self.entity_name = entity_name
        self.entity_id = entity_id
        super().__init__(f"{entity_name} '{entity_id}' {message}")

class NotFoundError(BaseDomainError):
    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(entity_name, entity_id, "not found")

class AlreadyExistsError(BaseDomainError):
    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(entity_name, entity_id, "already exists")

def create_exception_pair(entity_name: str):    
    class NotFound(NotFoundError):
        def __init__(self, entity_id: Any):
            super().__init__(entity_name, entity_id)
            
    class AlreadyExists(AlreadyExistsError):
        def __init__(self, entity_id: Any):
            super().__init__(entity_name, entity_id)            

    NotFound.__name__ = f"{entity_name}NotFoundError"
    AlreadyExists.__name__ = f"{entity_name}AlreadyExistsError"
    
    return NotFound, AlreadyExists


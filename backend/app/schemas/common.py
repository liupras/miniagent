#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-29
# @description: Shared Pydantic schemas used across all modules

from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field
from app.core.i18n.i18n import t

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
    """
    code: int = Field(200, description="Business status code, 200 = success")
    message: str = Field("success", description="Human-readable status message")
    data: Optional[T] = Field(None, description="Response payload")

    def model_post_init(self, __context: Any) -> None:
        if self.message == "success":
            object.__setattr__(self, "message", t("common.success"))
    

class BaseDomainError(Exception):
    """Business Logic Exception Base Class"""
    error_key = "base_error"

    def __init__(self, entity_name: str, entity_id: Any, message: str):
        self.entity_name = entity_name
        self.entity_id = entity_id
        super().__init__(f"{entity_name} '{entity_id}' {message}")

    def i18n_key(self, kind: str) -> str:
        """kind: 'not_found' | 'already_exists'"""
        prefix = self.entity_name.lower()
        return f"{prefix}.{kind}"
    
    def to_detail(self) -> str:
        return t(self.i18n_key(self.error_key), id=self.entity_id, entity=self.entity_name)

class NotFoundError(BaseDomainError):
    error_key = "not_found"
    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(entity_name, entity_id, self.error_key)

class AlreadyExistsError(BaseDomainError):
    error_key = "already_exists"
    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(entity_name, entity_id, self.error_key)

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-29
# @description: Shared Pydantic schemas used across all modules

from collections.abc import Mapping
from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field


def _translate(key: str, **kwargs: Any) -> str:
    """Import i18n lazily so shared schemas do not create an import cycle."""
    from app.core.i18n.i18n import t

    return t(key, **kwargs)

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
            object.__setattr__(self, "message", _translate("common.success"))
    

class BaseDomainError(Exception):
    """Base class for stable, localizable application errors.

    ``error_key`` may be either an entity-relative key (for example
    ``not_found``) or a complete i18n key (for example ``judge.timeout``).
    The optional ``cause`` is retained for diagnostics only and is never
    included in the localized client-facing detail.
    """

    error_key = "base_error"

    def __init__(
        self,
        entity_name: str | None = None,
        entity_id: Any = None,
        message: str | None = None,
        *,
        error_key: str | None = None,
        params: Mapping[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.entity_name = entity_name
        self.entity_id = entity_id
        self.error_key = error_key or type(self).error_key
        self.params = dict(params or {})
        self.cause = cause
        if cause is not None:
            self.__cause__ = cause

        diagnostic_message = message or self.error_key
        if entity_name is not None:
            diagnostic_message = f"{entity_name} '{entity_id}' {diagnostic_message}"
        super().__init__(diagnostic_message)

    def i18n_key(self, kind: str | None = None) -> str:
        """Return a complete i18n key for this error."""
        selected_key = kind or self.error_key
        if "." in selected_key or self.entity_name is None:
            return selected_key
        return f"{self.entity_name.lower()}.{selected_key}"

    def _translation_params(self) -> dict[str, Any]:
        params = {
            "id": self.entity_id,
            "entity": self.entity_name or "",
        }
        params.update(self.params)
        return params
    
    def to_detail(self) -> str:
        """Return localized, client-safe detail without exposing the cause."""
        params = self._translation_params()
        key = self.i18n_key()
        detail = _translate(key, **params)
        if detail != key:
            return detail

        fallback_key = f"entity.{self.error_key.rsplit('.', 1)[-1]}"
        fallback_detail = _translate(fallback_key, **params)
        if fallback_detail != fallback_key:
            return fallback_detail

        return _translate("common.failed")

class NotFoundError(BaseDomainError):
    error_key = "not_found"
    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(entity_name, entity_id, self.error_key)

class AlreadyExistsError(BaseDomainError):
    error_key = "already_exists"
    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(entity_name, entity_id, self.error_key)

class EmptyDataError(BaseDomainError):
    error_key = "empty_data"
    
    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(entity_name, entity_id, "has no valid data or chunks left")

class BadRequestError(BaseDomainError):
    error_key = "bad_request"
    
    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(entity_name, entity_id, "is a bad request")

class ReadOnlyError(BaseDomainError):
    error_key = "readonly"

    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(entity_name, entity_id, "is read-only")

class InvalidValueError(BaseDomainError):
    error_key = "invalid_value"

    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(entity_name, entity_id, "has an invalid value")

class InactiveError(BaseDomainError):
    error_key = "inactive"

    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(entity_name, entity_id, "is inactive and cannot be used")

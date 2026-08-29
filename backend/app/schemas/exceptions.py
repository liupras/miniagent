#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: system-level exceptions for the application, including infrastructure and domain errors.

from collections.abc import Mapping
from typing import Any

from app.core.i18n.i18n import t

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
        detail = t(key, **params)
        if detail != key:
            return detail

        fallback_key = f"entity.{self.error_key.rsplit('.', 1)[-1]}"
        fallback_detail = t(fallback_key, **params)
        if fallback_detail != fallback_key:
            return fallback_detail

        return t("common.failed")


class InfrastructureError(BaseDomainError):
    """Base class for failures isolated at an infrastructure boundary."""

    error_key = "infrastructure.error"

    def __init__(
        self,
        message: str,
        *,
        error_key: str | None = None,
        params: Mapping[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_key=error_key,
            params=params,
            cause=cause,
        )

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


class UnsupportedMediaTypeError(BaseDomainError):
    """The supplied media type cannot be processed by the application."""

    error_key = "entity.unsupported_media_type"

    def __init__(
        self,
        message: str,
        *,
        error_key: str | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, error_key=error_key, params=params)


class PermissionDeniedError(BaseDomainError):
    """The authenticated caller is not allowed to perform the operation."""

    error_key = "entity.permission_denied"

    def __init__(
        self,
        message: str,
        *,
        error_key: str | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, error_key=error_key, params=params)


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

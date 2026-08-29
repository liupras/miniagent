#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-30
# @description: Stable failures used by optional reranker construction.

from app.schemas.exceptions import BaseDomainError, InfrastructureError


class RerankerConfigurationError(BaseDomainError):
    error_key = "reranker.configuration_error"

    def __init__(self, message: str) -> None:
        super().__init__(message=message)


class RerankerLoadError(InfrastructureError):
    error_key = "reranker.load_failed"

    def __init__(
        self,
        message: str,
        *,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message, cause=cause)

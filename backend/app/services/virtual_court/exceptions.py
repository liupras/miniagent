#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: Stable application exceptions for VirtualCourt judge decisions.

from collections.abc import Mapping
from typing import Any

from app.schemas.exceptions import BaseDomainError


class JudgeServiceError(BaseDomainError):
    """Base class for expected judge-service failures."""

    error_key = "judge.failed"

    def __init__(
        self,
        message: str,
        *,
        params: Mapping[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message=message, params=params, cause=cause)


class JudgeConfigurationError(JudgeServiceError):
    """The dedicated judge agent or one of its dependencies is misconfigured."""

    error_key = "judge.configuration_error"


class JudgeUnavailableError(JudgeServiceError):
    """A required upstream service is temporarily unavailable."""

    error_key = "judge.unavailable"


class JudgeTimeoutError(JudgeServiceError):
    """The judge decision exceeded its configured deadline."""

    error_key = "judge.timeout"


class JudgeInvalidResponseError(JudgeServiceError):
    """The model output cannot be exposed as a valid judge decision."""

    error_key = "judge.invalid_response"

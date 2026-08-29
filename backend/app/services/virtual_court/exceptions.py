#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: Stable application exceptions for VirtualCourt judge decisions.


class JudgeServiceError(Exception):
    """Base class for expected judge-service failures."""


class JudgeConfigurationError(JudgeServiceError):
    """The dedicated judge agent or one of its dependencies is misconfigured."""


class JudgeUnavailableError(JudgeServiceError):
    """A required upstream service is temporarily unavailable."""


class JudgeTimeoutError(JudgeServiceError):
    """The judge decision exceeded its configured deadline."""


class JudgeInvalidResponseError(JudgeServiceError):
    """The model output cannot be exposed as a valid judge decision."""

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: Stable application exceptions for VirtualCourt generation services.

from app.schemas.exceptions import BaseDomainError


class JudgeServiceError(BaseDomainError):
    """Base class for expected judge-service failures."""

    error_key = "judge.failed"

    def __init__(
        self,
        *,
        params: dict | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(params=params, cause=cause)


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


class JudgeContextError(JudgeServiceError):
    """Complete input does not fit; never truncate courtroom records."""
    error_key = "judge.context_too_large"


class TranscriptServiceError(BaseDomainError):
    """Base class for expected transcript-generation failures."""

    error_key = "transcript.failed"

    def __init__(
        self,
        *,
        params: dict | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(params=params, cause=cause)


class TranscriptConfigurationError(TranscriptServiceError):
    """The dedicated transcript agent is missing or misconfigured."""

    error_key = "transcript.configuration_error"


class TranscriptUnavailableError(TranscriptServiceError):
    """The transcript model provider is temporarily unavailable."""

    error_key = "transcript.unavailable"


class TranscriptTimeoutError(TranscriptServiceError):
    """Transcript generation exceeded its shared deadline."""

    error_key = "transcript.timeout"


class TranscriptInvalidResponseError(TranscriptServiceError):
    """The model output cannot be exposed as a valid transcript."""

    error_key = "transcript.invalid_response"


class TranscriptContextError(TranscriptServiceError):
    """Complete transcript input does not fit and must not be truncated."""

    error_key = "transcript.context_too_large"


class PartyReplyServiceError(BaseDomainError):
    """Base class for expected party-reply failures."""

    error_key = "party_reply.failed"

    def __init__(
        self,
        *,
        params: dict | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(params=params, cause=cause)


class PartyReplyConfigurationError(PartyReplyServiceError):
    """The dedicated party responder is missing or misconfigured."""

    error_key = "party_reply.configuration_error"


class PartyReplyUnavailableError(PartyReplyServiceError):
    """The party-reply model provider is temporarily unavailable."""

    error_key = "party_reply.unavailable"


class PartyReplyTimeoutError(PartyReplyServiceError):
    """Party reply generation exceeded its shared deadline."""

    error_key = "party_reply.timeout"


class PartyReplyInvalidResponseError(PartyReplyServiceError):
    """The model output cannot be exposed as a valid party reply."""

    error_key = "party_reply.invalid_response"


class PartyReplyContextError(PartyReplyServiceError):
    """Complete party-reply input does not fit and must not be truncated."""

    error_key = "party_reply.context_too_large"

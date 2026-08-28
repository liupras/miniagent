"""Shared types for the VirtualCourt system-to-system protocol."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IntegrationModel(BaseModel):
    """Strict base model for the externally versioned contract."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ActorRole(StrEnum):
    JUDGE = "JUDGE"
    PLAINTIFF = "PLAINTIFF"
    DEFENDANT = "DEFENDANT"
    CLERK = "CLERK"
    SYSTEM = "SYSTEM"


class PartyRole(StrEnum):
    PLAINTIFF = "PLAINTIFF"
    DEFENDANT = "DEFENDANT"


class CaseContext(IntegrationModel):
    cause_of_action: str = Field(min_length=1, max_length=256)
    procedure: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=6000)
    claims: list[str] = Field(default_factory=list, max_length=20)
    defenses: list[str] = Field(default_factory=list, max_length=20)
    dispute_focuses: list[str] = Field(default_factory=list, max_length=20)


class EvidenceContext(IntegrationModel):
    offered_by: PartyRole
    name: str = Field(min_length=1, max_length=256)
    purpose: str = Field(default="", max_length=2000)


class StageSummary(IntegrationModel):
    stage_id: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=4000)


class CourtEvent(IntegrationModel):
    event_type: str = Field(min_length=1, max_length=64)
    actor: ActorRole
    step_id: str = Field(min_length=1, max_length=64)
    content: str = Field(default="", max_length=4000)


class IntegrationErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    MODEL_RESPONSE_INVALID = "MODEL_RESPONSE_INVALID"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class IntegrationError(IntegrationModel):
    code: IntegrationErrorCode
    message: str = Field(min_length=1, max_length=1000)
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class IntegrationErrorResponse(IntegrationModel):
    error: IntegrationError

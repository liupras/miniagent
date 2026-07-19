#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-19
# @description: Audit Context

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Optional
from uuid import uuid4


AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
AUDIT_EXCLUDED_PATHS = {
    "/api/v1/login",
    "/api/v1/refresh-token",
}


@dataclass
class AuditRequestContext:
    request_id: str
    method: str
    path: str
    ip_address: Optional[str] = None
    user_id: Optional[int] = None
    username: Optional[str] = None
    change_count: int = 0


_audit_context: ContextVar[Optional[AuditRequestContext]] = ContextVar(
    "audit_request_context", default=None
)


def begin_audit_context(
    method: str,
    path: str,
    ip_address: Optional[str] = None,
) -> Optional[Token]:
    """Start audit collection for state-changing API requests."""
    normalized_method = method.upper()
    if (
        normalized_method not in AUDITED_METHODS
        or path in AUDIT_EXCLUDED_PATHS
        or not path.startswith("/api/")
    ):
        return None

    return _audit_context.set(
        AuditRequestContext(
            request_id=str(uuid4()),
            method=normalized_method,
            path=path,
            ip_address=ip_address,
        )
    )


def reset_audit_context(token: Optional[Token]) -> None:
    if token is not None:
        _audit_context.reset(token)


def get_audit_context() -> Optional[AuditRequestContext]:
    return _audit_context.get()


def set_audit_user(user_id: int, username: str) -> None:
    """Attach the identity resolved by the central auth dependency."""
    context = get_audit_context()
    if context is not None:
        context.user_id = user_id
        context.username = username


def mark_audit_change(count: int = 1) -> None:
    context = get_audit_context()
    if context is not None:
        context.change_count += count

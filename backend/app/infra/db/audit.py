#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-19
# @description: Audit DB

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import math
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from loguru import logger
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.core.audit_context import get_audit_context, mark_audit_change
from app.infra.db.database import AuditLog

if TYPE_CHECKING:
    from app.repositories.async_audit_log import AsyncAuditLogDatabase


_PENDING_KEY = "_audit_pending_changes"
_SENSITIVE_PARTS = {
    "password",
    "passwd",
    "api_key",
    "apikey",
    "token",
    "secret",
    "authorization",
    "credential",
}
_MAX_STRING_LENGTH = 4000
_MAX_COLLECTION_ITEMS = 100
_listeners_installed = False


def _is_sensitive(key: str) -> bool:
    normalized = key.lower()
    return any(part in normalized for part in _SENSITIVE_PARTS)


def _json_safe(value: Any, key: str = "") -> Any:
    if key and _is_sensitive(key):
        return "***REDACTED***"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, str):
        if len(value) <= _MAX_STRING_LENGTH:
            return value
        omitted = len(value) - _MAX_STRING_LENGTH
        return f"{value[:_MAX_STRING_LENGTH]}... <{omitted} chars omitted>"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID, Enum)):
        return str(value.value if isinstance(value, Enum) else value)
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, dict):
        items = list(value.items())[:_MAX_COLLECTION_ITEMS]
        result = {str(k): _json_safe(v, str(k)) for k, v in items}
        if len(value) > _MAX_COLLECTION_ITEMS:
            result["__audit_truncated__"] = len(value) - _MAX_COLLECTION_ITEMS
        return result
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        result = [_json_safe(item) for item in items[:_MAX_COLLECTION_ITEMS]]
        if len(items) > _MAX_COLLECTION_ITEMS:
            result.append(
                f"<{len(items) - _MAX_COLLECTION_ITEMS} items omitted>"
            )
        return result
    return str(value)


def _snapshot(instance: Any) -> dict[str, Any]:
    state = inspect(instance)
    snapshot = {
        column.key: _json_safe(getattr(instance, column.key, None), column.key)
        for column in state.mapper.columns
    }
    # Key-value tables often keep secrets in a generic `value` column.
    semantic_key = str(snapshot.get("key", ""))
    if _is_sensitive(semantic_key) and "value" in snapshot:
        snapshot["value"] = "***REDACTED***"
    return snapshot


def _before_update_snapshot(instance: Any) -> dict[str, Any]:
    state = inspect(instance)
    before = _snapshot(instance)
    for column in state.mapper.columns:
        history = state.attrs[column.key].history
        if history.has_changes() and history.deleted:
            before[column.key] = _json_safe(history.deleted[0], column.key)
    semantic_key = str(before.get("key", ""))
    if _is_sensitive(semantic_key) and "value" in before:
        before["value"] = "***REDACTED***"
    return before


def _target_id(instance: Any) -> str:
    state = inspect(instance)
    values = [getattr(instance, column.key, None) for column in state.mapper.primary_key]
    populated = [str(value) for value in values if value is not None]
    return ":".join(populated) if populated else "<unknown>"


def _before_flush(session: Session, _flush_context: Any, _instances: Any) -> None:
    context = get_audit_context()
    if context is None:
        return

    pending = session.info.setdefault(_PENDING_KEY, [])
    for instance in list(session.new):
        if not isinstance(instance, AuditLog):
            pending.append(("CREATE", instance, None))

    for instance in list(session.dirty):
        if isinstance(instance, AuditLog) or not session.is_modified(
            instance, include_collections=False
        ):
            continue
        pending.append(("UPDATE", instance, _before_update_snapshot(instance)))

    for instance in list(session.deleted):
        if not isinstance(instance, AuditLog):
            pending.append(("DELETE", instance, _snapshot(instance)))


def _after_flush_postexec(session: Session, _flush_context: Any) -> None:
    context = get_audit_context()
    pending = session.info.pop(_PENDING_KEY, [])
    if context is None or not pending:
        return

    for action, instance, before_value in pending:
        after_value = None if action == "DELETE" else _snapshot(instance)
        session.add(
            AuditLog(
                request_id=context.request_id,
                user_id=context.user_id,
                username=context.username,
                ip_address=context.ip_address,
                target_type=instance.__class__.__name__[:50],
                target_id=_target_id(instance)[:100],
                action=action,
                before_value=before_value,
                after_value=after_value,
                description=f"{context.method} {context.path}",
                status="success",
            )
        )

    mark_audit_change(len(pending))


def _clear_pending(session: Session) -> None:
    session.info.pop(_PENDING_KEY, None)


def install_audit_listeners() -> None:
    """Install listeners once for sync Sessions and AsyncSession proxies."""
    global _listeners_installed
    if _listeners_installed:
        return
    event.listen(Session, "before_flush", _before_flush)
    event.listen(Session, "after_flush_postexec", _after_flush_postexec)
    event.listen(Session, "after_rollback", _clear_pending)
    _listeners_installed = True
    logger.info("SQLAlchemy audit listeners installed.")


def infer_request_action(method: str, path: str) -> str:
    if method == "DELETE":
        return "DELETE"
    if method in {"PUT", "PATCH"}:
        return "UPDATE"
    execute_markers = ("execute", "run", "query", "search", "retrieve", "import")
    if any(marker in path.lower() for marker in execute_markers):
        return "EXECUTE"
    return "CREATE"


def infer_request_target(
    route_name: Optional[str], path_params: dict[str, Any], path: str
) -> tuple[str, str]:
    target_type = route_name or path.rstrip("/").rsplit("/", 1)[-1] or "Request"
    target_id = next(
        (str(value) for value in path_params.values() if value is not None),
        "batch" if path_params else "-",
    )
    return target_type, target_id


async def record_request_outcome(
    audit_log_db: "AsyncAuditLogDatabase",
    *,
    status_code: int,
    route_name: Optional[str],
    path_params: dict[str, Any],
) -> None:
    """Record failures and successful non-ORM operations in a separate transaction."""
    context = get_audit_context()
    if context is None:
        return

    failed = status_code >= 400
    action = infer_request_action(context.method, context.path)
    if not failed and context.change_count > 0 and action != "EXECUTE":
        return

    target_type, target_id = infer_request_target(
        route_name, path_params, context.path
    )
    await audit_log_db.create(
        request_id=context.request_id,
        user_id=context.user_id,
        username=context.username,
        ip_address=context.ip_address,
        target_type=target_type[:50],
        target_id=target_id[:100],
        action=action,
        description=f"{context.method} {context.path} - HTTP {status_code}",
        status="failure" if failed else "success",
    )

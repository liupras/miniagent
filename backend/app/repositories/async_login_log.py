#!/usr/bin/python
# -*- coding:utf-8 -*-

from __future__ import annotations

from typing import Optional

from app.infra.db.async_base import AsyncBaseDatabase
from app.infra.db.database import LoginLog


class AsyncLoginLogDatabase(AsyncBaseDatabase):
    """Asynchronous persistence for login and token-refresh events."""

    async def create(
        self,
        *,
        request_id: str,
        event_type: str,
        success: bool,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> LoginLog:
        async with self.get_session() as session:
            row = LoginLog(
                request_id=request_id[:36],
                event_type=event_type[:20],
                user_id=user_id,
                username=username[:100] if username else None,
                ip_address=ip_address[:50] if ip_address else None,
                user_agent=user_agent,
                success=success,
                failure_reason=failure_reason,
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return row

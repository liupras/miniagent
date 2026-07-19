#!/usr/bin/python
# -*- coding:utf-8 -*-

from __future__ import annotations

from typing import Optional

from app.infra.db.database import LoginLog
from app.repositories.async_login_log import AsyncLoginLogDatabase


class LoginLogService:
    def __init__(self, db: AsyncLoginLogDatabase) -> None:
        self._db = db

    async def record(
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
        return await self._db.create(
            request_id=request_id,
            event_type=event_type,
            success=success,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            failure_reason=failure_reason,
        )

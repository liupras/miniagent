#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-19
# @description: Login Log

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_, select

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

    async def get(self, login_log_id: int) -> Optional[LoginLog]:
        async with self.get_session() as session:
            return await session.get(LoginLog, login_log_id)

    async def list_logs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        request_id: Optional[str] = None,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        event_type: Optional[str] = None,
        success: Optional[bool] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
    ) -> tuple[list[LoginLog], int]:
        filters = []
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(
                or_(
                    LoginLog.request_id.ilike(pattern),
                    LoginLog.username.ilike(pattern),
                    LoginLog.ip_address.ilike(pattern),
                    LoginLog.user_agent.ilike(pattern),
                    LoginLog.failure_reason.ilike(pattern),
                )
            )
        if request_id:
            filters.append(LoginLog.request_id == request_id)
        if user_id is not None:
            filters.append(LoginLog.user_id == user_id)
        if username:
            filters.append(LoginLog.username.ilike(f"%{username.strip()}%"))
        if ip_address:
            filters.append(LoginLog.ip_address.ilike(f"%{ip_address.strip()}%"))
        if event_type:
            filters.append(LoginLog.event_type == event_type)
        if success is not None:
            filters.append(LoginLog.success.is_(success))
        if created_from:
            filters.append(LoginLog.created_at >= created_from)
        if created_to:
            filters.append(LoginLog.created_at <= created_to)

        async with self.get_session() as session:
            total = await session.scalar(
                select(func.count(LoginLog.id)).where(*filters)
            )
            result = await session.execute(
                select(LoginLog)
                .where(*filters)
                .order_by(LoginLog.created_at.desc(), LoginLog.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            return list(result.scalars().all()), int(total or 0)

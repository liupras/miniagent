#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-19
# @description: Audit Log Repo

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, or_, select

from app.infra.db.async_base import AsyncBaseDatabase
from app.infra.db.database import AuditLog


class AsyncAuditLogDatabase(AsyncBaseDatabase):
    """Asynchronous repository for request-level audit records."""

    async def create(
        self,
        *,
        request_id: str,
        target_type: str,
        target_id: str,
        action: str,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        before_value: Optional[dict[str, Any]] = None,
        after_value: Optional[dict[str, Any]] = None,
        description: Optional[str] = None,
        status: str = "success",
    ) -> AuditLog:
        async with self.get_session() as session:
            row = AuditLog(
                request_id=request_id[:36],
                user_id=user_id,
                username=username[:100] if username else None,
                ip_address=ip_address[:50] if ip_address else None,
                target_type=target_type[:50],
                target_id=target_id[:100],
                action=action[:20],
                before_value=before_value,
                after_value=after_value,
                description=description,
                status=status[:20],
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return row

    async def get(self, audit_id: int) -> Optional[AuditLog]:
        async with self.get_session() as session:
            return await session.get(AuditLog, audit_id)

    async def list_logs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        request_id: Optional[str] = None,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        action: Optional[str] = None,
        status: Optional[str] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
    ) -> tuple[list[AuditLog], int]:
        filters = []
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(
                or_(
                    AuditLog.request_id.ilike(pattern),
                    AuditLog.username.ilike(pattern),
                    AuditLog.target_type.ilike(pattern),
                    AuditLog.target_id.ilike(pattern),
                    AuditLog.description.ilike(pattern),
                )
            )
        if request_id:
            filters.append(AuditLog.request_id == request_id)
        if user_id is not None:
            filters.append(AuditLog.user_id == user_id)
        if username:
            filters.append(AuditLog.username.ilike(f"%{username.strip()}%"))
        if target_type:
            filters.append(AuditLog.target_type == target_type)
        if target_id:
            filters.append(AuditLog.target_id == target_id)
        if action:
            filters.append(AuditLog.action == action)
        if status:
            filters.append(AuditLog.status == status)
        if created_from:
            filters.append(AuditLog.created_at >= created_from)
        if created_to:
            filters.append(AuditLog.created_at <= created_to)

        async with self.get_session() as session:
            total = await session.scalar(
                select(func.count(AuditLog.id)).where(*filters)
            )
            result = await session.execute(
                select(AuditLog)
                .where(*filters)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            return list(result.scalars().all()), int(total or 0)

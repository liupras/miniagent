#!/usr/bin/python
# -*- coding:utf-8 -*-

from datetime import datetime
from typing import Optional

from app.repositories.async_audit_log import AsyncAuditLogDatabase
from app.schemas.admin.audit_log import AuditLogOut
from app.schemas.common import NotFoundError, PageResult


class AuditLogNotFoundError(NotFoundError):
    def __init__(self, audit_id: int) -> None:
        super().__init__("AuditLog", audit_id)


class AuditLogService:
    def __init__(self, db: AsyncAuditLogDatabase) -> None:
        self._db = db

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
    ) -> PageResult[AuditLogOut]:
        rows, total = await self._db.list_logs(
            page=page,
            page_size=page_size,
            keyword=keyword,
            request_id=request_id,
            user_id=user_id,
            username=username,
            target_type=target_type,
            target_id=target_id,
            action=action,
            status=status,
            created_from=created_from,
            created_to=created_to,
        )
        return PageResult(
            total=total,
            page=page,
            page_size=page_size,
            data=[AuditLogOut.model_validate(row) for row in rows],
        )

    async def get(self, audit_id: int) -> AuditLogOut:
        row = await self._db.get(audit_id)
        if row is None:
            raise AuditLogNotFoundError(audit_id)
        return AuditLogOut.model_validate(row)

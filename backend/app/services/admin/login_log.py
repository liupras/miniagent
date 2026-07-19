#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-19
# @description: Login Log

from datetime import datetime
from typing import Optional

from app.repositories.async_login_log import AsyncLoginLogDatabase
from app.schemas.admin.login_log import LoginLogOut
from app.schemas.common import NotFoundError, PageResult


class LoginLogNotFoundError(NotFoundError):
    def __init__(self, login_log_id: int) -> None:
        super().__init__("LoginLog", login_log_id)


class LoginLogAdminService:
    def __init__(self, db: AsyncLoginLogDatabase) -> None:
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
        ip_address: Optional[str] = None,
        event_type: Optional[str] = None,
        success: Optional[bool] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
    ) -> PageResult[LoginLogOut]:
        rows, total = await self._db.list_logs(
            page=page,
            page_size=page_size,
            keyword=keyword,
            request_id=request_id,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            event_type=event_type,
            success=success,
            created_from=created_from,
            created_to=created_to,
        )
        return PageResult(
            total=total,
            page=page,
            page_size=page_size,
            data=[LoginLogOut.model_validate(row) for row in rows],
        )

    async def get(self, login_log_id: int) -> LoginLogOut:
        row = await self._db.get(login_log_id)
        if row is None:
            raise LoginLogNotFoundError(login_log_id)
        return LoginLogOut.model_validate(row)

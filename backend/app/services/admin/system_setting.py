#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-26
# @description: System Setting

import json
import math
from typing import Optional

from loguru import logger

from app.repositories.async_system_setting import AsyncSystemSettingDatabase
from app.schemas.admin.system_setting import SystemSettingOut, SystemSettingUpdate
from app.schemas.common import InvalidValueError, NotFoundError, ReadOnlyError


class SystemSettingNotFoundError(NotFoundError):
    def __init__(self, key: str) -> None:
        super().__init__("SystemSetting", key)


class SystemSettingReadOnlyError(ReadOnlyError):
    def __init__(self, key: str) -> None:
        super().__init__("SystemSetting", key)


class SystemSettingValueError(InvalidValueError):
    def __init__(self, key: str) -> None:
        super().__init__("SystemSetting", key)


class SystemSettingService:

    _language = "zh_CN"

    def __init__(self, db: AsyncSystemSettingDatabase) -> None:
        self._db = db

    async def get_system_language(self) -> str:
        """
        Read the global system language from SystemSettings via AsyncSystemSettingDatabase.
        """
        try:
            return await self._db.get_language(fallback=self._language)
        except Exception as exc:
            logger.error(
                f"[get_system_language] DB read failed: {exc} "
                f"— using fallback '{self._language}'"
            )
        return self._language

    async def set_system_language(self, lang: str) -> bool:

        result = await self._db.set_language(lang)
        if result:
            self._language = lang.strip()

        return result

    async def list_settings(
        self, group: Optional[str] = None
    ) -> list[SystemSettingOut]:
        rows = (
            await self._db.get_by_group(group.strip())
            if group and group.strip()
            else await self._db.get_all()
        )
        return [SystemSettingOut.model_validate(row) for row in rows]

    async def get_setting(self, key: str) -> SystemSettingOut:
        row = await self._db.get(key)
        if row is None:
            raise SystemSettingNotFoundError(key)
        return SystemSettingOut.model_validate(row)

    async def update_setting(
        self, key: str, payload: SystemSettingUpdate
    ) -> SystemSettingOut:
        row = await self._db.get(key)
        if row is None:
            raise SystemSettingNotFoundError(key)
        if row.is_readonly:
            raise SystemSettingReadOnlyError(key)

        value = self._validate_value(key, payload.value, row.value_type)
        if not await self._db.set(key, value):
            # Protect the service contract if the row changes concurrently.
            raise SystemSettingReadOnlyError(key)

        if key == "system_language":
            self._language = value
        return await self.get_setting(key)

    @staticmethod
    def _validate_value(key: str, value: str, value_type: str) -> str:
        if value_type == "string":
            return value

        normalized = value.strip()
        try:
            if value_type == "int":
                int(normalized)
            elif value_type == "float":
                if not math.isfinite(float(normalized)):
                    raise ValueError("non-finite float")
            elif value_type == "bool":
                lowered = normalized.lower()
                if lowered not in {"true", "false"}:
                    raise ValueError("boolean must be true or false")
                return lowered
            elif value_type == "json":
                json.loads(normalized)
            else:
                raise ValueError(f"unsupported value type: {value_type}")
        except (TypeError, ValueError, json.JSONDecodeError):
            raise SystemSettingValueError(key) from None
        return normalized

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: SystemSetting Database Management (Asynchronous)

from typing import Dict, List, Optional
from loguru import logger
from sqlalchemy import select

from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import SystemSetting


# ─────────────────────────────────────────────────────────────────────────────
# SystemSetting
# ─────────────────────────────────────────────────────────────────────────────

class AsyncSystemSettingDatabase(AsyncBaseDatabase):
    """
    CRUD operations for the SystemSetting table (Asynchronous).

    SystemSetting is a key-value store for global configuration.
    All values are stored as strings; callers handle type conversion.
    """

    # ── Read ──────────────────────────────────────────────────────────────

    async def get(self, key: str) -> Optional[SystemSetting]:
        """
        Return the SystemSetting row for *key*, or None if not found.
        """
        async with self.get_session() as session:
            row = await session.get(SystemSetting, key)

        if row is None:
            logger.warning(f"[DB] SystemSetting key not found: '{key}'")
        else:
            logger.debug(f"[DB] SystemSetting get: key='{key}' value='{row.value}'")
        return row

    async def get_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Return the plain string value for *key*, or *default* if not found.
        """
        row = await self.get(key)
        return row.value if row is not None else default

    async def get_language(self, fallback: str = "zh") -> str:
        """
        Return the current system language tag (lower-cased).
        """
        value = await self.get_value("system_language", fallback)
        return (value or fallback).strip().lower()

    async def get_all(self) -> List[SystemSetting]:
        """
        Return all rows ordered by group then key.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(SystemSetting)
                .order_by(SystemSetting.group, SystemSetting.key)
            )
            rows = result.scalars().all()

        logger.debug(f"[DB] SystemSetting get_all: found={len(rows)}")
        return list(rows)

    async def get_by_group(self, group: str) -> List[SystemSetting]:
        """
        Return all settings in *group*, ordered by key.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(SystemSetting)
                .where(SystemSetting.group == group)
                .order_by(SystemSetting.key)
            )
            rows = result.scalars().all()

        logger.debug(
            f"[DB] SystemSetting get_by_group: group='{group}' found={len(rows)}"
        )
        return list(rows)

    async def as_dict(self) -> Dict[str, str]:
        """
        Return all settings as a plain {key: value} dict.
        """
        rows = await self.get_all()
        return {row.key: row.value for row in rows}

    # ── Write ─────────────────────────────────────────────────────────────

    async def set(self, key: str, value: str) -> bool:
        """
        Update the value of an existing setting.
        """
        async with self.get_session() as session:
            row = await session.get(SystemSetting, key)

            if row is None:
                logger.warning(f"[DB] SystemSetting.set: key not found '{key}'")
                return False

            if row.is_readonly:
                logger.warning(
                    f"[DB] SystemSetting.set: key '{key}' is read-only, skipped"
                )
                return False

            old_value = row.value
            row.value = value

        logger.info(
            f"[DB] SystemSetting updated: key='{key}' '{old_value}' → '{value}'"
        )
        return True

    async def set_language(self, lang: str) -> bool:
        """
        Convenience wrapper to update system_language.
        """
        return await self.set("system_language", lang.strip().lower())

    async def set_many(self, updates: Dict[str, str]) -> Dict[str, bool]:
        """
        Update multiple settings in a single transaction.
        """
        results: Dict[str, bool] = {}

        async with self.get_session() as session:
            for key, value in updates.items():
                row = await session.get(SystemSetting, key)

                if row is None:
                    logger.warning(
                        f"[DB] SystemSetting.set_many: key not found '{key}'"
                    )
                    results[key] = False
                    continue

                if row.is_readonly:
                    logger.warning(
                        f"[DB] SystemSetting.set_many: key '{key}' is read-only, skipped"
                    )
                    results[key] = False
                    continue

                row.value = value
                results[key] = True
                logger.debug(f"[DB] SystemSetting.set_many: '{key}' → '{value}'")

        logger.info(
            f"[DB] SystemSetting.set_many: "
            f"{sum(results.values())}/{len(updates)} updated"
        )
        return results
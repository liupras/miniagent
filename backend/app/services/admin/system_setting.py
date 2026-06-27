#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-26
# @description: System Setting

from loguru import logger

from app.repositories.async_system_setting import AsyncSystemSettingDatabase

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

    async def set_system_language(self, lang)->bool:

        result = await self._db.set_language(           
            lang,
        )
        self._language = lang

        return result
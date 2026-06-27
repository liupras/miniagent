#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-27
# @description: I18n

from pathlib import Path
import yaml

from loguru import logger
from app.services.admin.system_setting import SystemSettingService

translations = {}

class I18n:
    def __init__(self, setting_service:SystemSettingService):

        self._setting_service = setting_service
        self._language = "zh_CN"

    @classmethod
    async def create(cls, setting_service:SystemSettingService):
        instance = cls(setting_service)
        await instance.initialize()
        return instance
    
    async def initialize(self) -> None:
        global translations
        try:
            self._language = await self._setting_service.get_system_language()
            logger.debug(f"I8n's language is {self._language}.")

            locale_file = Path(f"app/locales/{self._language}.yaml")
            
            if locale_file.exists():
                with open(locale_file, "r", encoding="utf-8") as f:
                    translations = yaml.safe_load(f) or {}
                logger.debug(f"Locales for '{self._language}' are successfully loaded.")
            else:
                logger.warning(f"[I18n] Locale file not found: {locale_file}")
                translations = {}
        except Exception as exc:
            # Non-fatal: fall through to built-in fallbacks.
            logger.warning(
                f"[I18n] Failed to load locale from File "
                f"(lang='{self._language}'): {exc}  — using built-in fallbacks."
            )


def t(key: str, **kwargs):
    if not isinstance(translations, dict):
        return key
    
    data = translations
    for k in key.split("."):        
        if isinstance(data, dict):
            data = data.get(k)
        else:
            return key

        if data is None:
            return key

    text = str(data) if not isinstance(data, dict) else key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            logger.warning(f"[I18n] Format failed for key '{key}' with {kwargs}")
    return text
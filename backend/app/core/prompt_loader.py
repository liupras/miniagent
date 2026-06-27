#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-15
# @description: Prompt-aware prompt resolution

from typing import Dict
from loguru import logger

from app.services.admin.system_setting import SystemSettingService
from app.services.admin.prompt import PromptService

class PromptLoader:

    def __init__(self, setting_service:SystemSettingService,prompt_service:PromptService):
        
        self._setting_service = setting_service
        self._prompt_service = prompt_service

        self._templates: Dict[str, Dict[str, str]] = {}
        self._language = "zh_CN"

    @classmethod
    async def create(cls, setting_service:SystemSettingService,prompt_service:PromptService):
        instance = cls(setting_service,prompt_service)
        await instance.initialize()
        return instance

    async def initialize(self) -> None:
        """
        Bulk-load all prompt templates for self.lang from the Prompt table.
        """
        try:
            self._language = await self._setting_service.get_system_language()
            logger.debug(f"system language is {self._language}.")

            self._templates = await self._prompt_service.get_all_as_dict()            
            logger.debug(
                f"[PromptLoader] Loaded {len(self._templates)} prompt(s) "
                f"for lang='{self._language}' from Prompt table."
            )
        except Exception as exc:
            # Non-fatal: fall through to built-in fallbacks.
            logger.warning(
                f"[PromptLoader] Failed to load prompts from Prompt table "
                f"(lang='{self._language}'): {exc}  — using built-in fallbacks."
            )

    def get(self, key: str) -> str:
        """
        Return the resolved template for *key* in the active language.
        """
        value = self._templates.get(key, {}).get(self._language, "")

        if not value:
            logger.error(
                f"[PromptLoader] Unknown prompt key='{key}' — returning empty string."
            )
        return value
    
# Global Instance
prompt_loader: PromptLoader | None = None
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-15
# @description: Prompt-aware prompt resolution

from typing import Dict

from loguru import logger

from app.repositories import AsyncSystemSettingDatabase,AsyncPromptDatabase

async def get_system_language(setting_db:AsyncSystemSettingDatabase,fallback: str = "zh_CN") -> str:
    """
    Read the global system language from SystemSettings via AsyncSystemSettingDatabase.
    """
    try:
        return await setting_db.get_language(fallback=fallback)
    except Exception as exc:
        logger.warning(
            f"[get_system_language] DB read failed: {exc} "
            f"— using fallback '{fallback}'"
        )
    return fallback

# ═══════════════════════════════════════════════════════════════════════════
# PromptLoader  —  Prompt-aware prompt resolution
# ═══════════════════════════════════════════════════════════════════════════
class PromptLoader:

    def __init__(self, lang: str,db:AsyncPromptDatabase):
        
        self._lang = lang.lower().strip()
        self._db = db
        self._templates: Dict[str, str] = {}

    @classmethod
    async def create(cls, lang: str, db:AsyncPromptDatabase):
        instance = cls(lang,db)
        await instance._load_from_db()
        return instance

    async def _load_from_db(self) -> None:
        """
        Bulk-load all prompt templates for self.lang from the Prompt table.
        """
        try:
            self._templates = await self._db.as_dict_for_group_lang("prompt", self._lang)
            logger.debug(
                f"[PromptLoader] Loaded {len(self._templates)} prompt(s) "
                f"for lang='{self._lang}' from Prompt table."
            )
        except Exception as exc:
            # Non-fatal: fall through to built-in fallbacks.
            logger.warning(
                f"[PromptLoader] Failed to load prompts from Prompt table "
                f"(lang='{self._lang}'): {exc}  — using built-in fallbacks."
            )

    def get(self, key: str) -> str:
        """
        Return the resolved template for *key* in the active language.
        """
        # 1. DB
        if key in self._templates:
            return self._templates[key]

        logger.error(
            f"[PromptLoader] Unknown prompt key='{key}' — returning empty string."
        )
        return ""
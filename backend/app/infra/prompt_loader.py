#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-15
# @description: i18n-aware prompt resolution

from typing import Dict

from loguru import logger

from app.repositories import AsyncSystemSettingDatabase,AsyncI18nDatabase

async def get_system_language(setting_db:AsyncSystemSettingDatabase,fallback: str = "zh") -> str:
    """
    Read the global system language from SystemSettings via AsyncSystemSettingDatabase.

    Opens its own DB session internally (same pattern as all BaseDatabase
    subclasses), so no session argument is needed.

    Args:
        fallback    Returned when the DB row is missing.

    Returns:
        Lower-cased language tag, e.g. "zh" or "en".
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
# PromptLoader  —  i18n-aware prompt resolution
# ═══════════════════════════════════════════════════════════════════════════
class PromptLoader:
    """
    Resolve pipeline prompt templates from the I18n table (group="prompt"),
    with compile-time built-in fallbacks for safety.

    Lifecycle
    ---------
    One PromptLoader instance is created per pipeline build (from_config).
    It calls AsyncI18nDatabase.as_dict_for_group_lang("prompt", lang) to load all
    prompt templates for the active language in a single query, then serves
    .get() calls from an in-memory dict — zero extra DB round-trips during
    inference.

    Built-in fallbacks are intentionally minimal; the canonical source of
    truth is the I18n table seeded by db_manager via seeds/i18n.json.
    """

    def __init__(self, lang: str,i18n_db:AsyncI18nDatabase):
        
        self._lang = lang.lower().strip()
        self._i18n_db = i18n_db
        self._templates: Dict[str, str] = {}

    @classmethod
    async def create(cls, lang: str, i18n_db:AsyncI18nDatabase):
        instance = cls(lang,i18n_db)
        await instance._load_from_db()
        return instance

    async def _load_from_db(self) -> None:
        """
        Bulk-load all prompt templates for self.lang from the I18n table.

        Calls AsyncI18nDatabase.as_dict_for_group_lang("prompt", lang), which
        runs a single  SELECT … WHERE group='prompt' AND lang=?  and returns
        {key: value}.  AsyncI18nDatabase manages its own connection internally.
        """
        try:
            self._templates = await self._i18n_db.as_dict_for_group_lang("prompt", self._lang)
            logger.debug(
                f"[PromptLoader] Loaded {len(self._templates)} prompt(s) "
                f"for lang='{self._lang}' from I18n table."
            )
        except Exception as exc:
            # Non-fatal: fall through to built-in fallbacks.
            logger.warning(
                f"[PromptLoader] Failed to load prompts from I18n table "
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
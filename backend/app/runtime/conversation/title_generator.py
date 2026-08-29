#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-07
# @description: Conversation Title Generator

from __future__ import annotations

from .cleaner import TitleCleaner
from .keyword_extractor import KeywordExtractor
from .config import load_config
from app.schemas.exceptions import BaseDomainError


class TitleGenerationError(BaseDomainError):
    """A known failure reported by a conversation title capability."""

    error_key = "conversation.title_generation_failed"

    def __init__(self, *, cause: BaseException | None = None) -> None:
        super().__init__(
            message="Conversation title generation failed",
            cause=cause,
        )

class ConversationTitleGenerator:
    """
    Conversation title generator.

    Strategy

        1. Cleaner
        2. Keyword Extractor
        3. Default Title
    """

    def __init__(self):

        self.config = load_config()

        self._bad_titles = {
            title.lower()
            for title in self.config.bad_titles
        }

    def generate(
        self,
        text: str,
    ) -> str:

        title = self._generate_by_cleaner(text)

        if self._is_valid(title):
            return title

        title = self._generate_by_keywords(text)

        if self._is_valid(title):
            return title

        return self.config.default_title

    # -------------------------------------------------------------------------

    def _generate_by_cleaner(
        self,
        text: str,
    ) -> str:

        zh = self.config.languages.get("zh")

        en = self.config.languages.get("en")

        return TitleCleaner.clean(
            text=text,
            zh_prefixes=zh.prefixes if zh else [],
            en_prefixes=en.prefixes if en else [],
            en_patterns=en.patterns if en else [],
            trim_chars=self.config.trim_chars,
            max_length=self.config.max_length,
        )

    # -------------------------------------------------------------------------

    def _generate_by_keywords(
        self,
        text: str,
    ) -> str:

        title = KeywordExtractor.extract(text)

        if not title:
            return ""

        return title[: self.config.max_title_length].strip()

    # -------------------------------------------------------------------------

    def _is_valid(
        self,
        title: str,
    ) -> bool:

        if not title:
            return False

        title = title.strip()

        if not title:
            return False

        if len(title) < 2:
            return False

        if title.lower() in self._bad_titles:
            return False

        return True

# Global Instance    
title_generator = ConversationTitleGenerator()

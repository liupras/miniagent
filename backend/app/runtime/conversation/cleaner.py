#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-07
# @description: Title cleaner

from __future__ import annotations

import re


class TitleCleaner:
    """
    Conversation title cleaner.

    Responsibilities:

        - Remove code blocks
        - Remove inline code
        - Remove markdown
        - Remove URLs
        - Remove emojis
        - Normalize whitespace
        - Keep first sentence
        - Remove Chinese prefixes
        - Remove English prefixes
        - Remove English question patterns
        - Trim punctuation
        - Limit length
    """

    _EMOJI_RE = re.compile(
        "["
        "\U0001F300-\U0001FAFF"
        "\U00002600-\U000026FF"
        "\U00002700-\U000027BF"
        "]+",
        flags=re.UNICODE,
    )

    _URL_RE = re.compile(r"https?://\S+")

    _CODE_BLOCK_RE = re.compile(
        r"```.*?```",
        flags=re.S,
    )

    _INLINE_CODE_RE = re.compile(
        r"`([^`]*)`"
    )

    _MARKDOWN_RE = re.compile(
        r"[*_>#]+"
    )

    _SPACE_RE = re.compile(r"\s+")

    _FIRST_SENTENCE_RE = re.compile(
        r"[。！？.!?\n]"
    )

    @classmethod
    def clean(
        cls,
        text: str,
        *,
        zh_prefixes: list[str],
        en_prefixes: list[str],
        en_patterns: list[str],
        trim_chars: str,
        max_length: int,
    ) -> str:
        """
        Clean conversation title.

        Args:
            text:
                Raw user message.

            zh_prefixes:
                Chinese prefixes.

            en_prefixes:
                English prefixes.

            en_patterns:
                English regex patterns.

            trim_chars:
                Characters trimmed from both ends.

            max_length:
                Maximum output length.

        Returns:
            Clean title.
        """

        if not text:
            return ""

        text = text.strip()

        if not text:
            return ""

        # --------------------------------------------------
        # Remove code block
        # --------------------------------------------------

        text = cls._CODE_BLOCK_RE.sub("", text)

        # --------------------------------------------------
        # Remove inline code
        # --------------------------------------------------

        text = cls._INLINE_CODE_RE.sub(
            r"\1",
            text,
        )

        # --------------------------------------------------
        # Remove URL
        # --------------------------------------------------

        text = cls._URL_RE.sub(
            "",
            text,
        )

        # --------------------------------------------------
        # Remove markdown
        # --------------------------------------------------

        text = cls._MARKDOWN_RE.sub(
            "",
            text,
        )

        # --------------------------------------------------
        # Remove emoji
        # --------------------------------------------------

        text = cls._EMOJI_RE.sub(
            "",
            text,
        )

        # --------------------------------------------------
        # Normalize whitespace
        # --------------------------------------------------

        text = cls._SPACE_RE.sub(
            " ",
            text,
        ).strip()

        # --------------------------------------------------
        # Keep first sentence
        # --------------------------------------------------

        parts = cls._FIRST_SENTENCE_RE.split(
            text,
            maxsplit=1,
        )

        if parts:
            text = parts[0].strip()

        # --------------------------------------------------
        # Remove Chinese prefixes
        # --------------------------------------------------

        for prefix in zh_prefixes:

            if text.startswith(prefix):

                text = text[len(prefix):].strip()

                break

        # --------------------------------------------------
        # Remove English prefixes
        # --------------------------------------------------

        lower = text.lower()

        for prefix in en_prefixes:

            if lower.startswith(prefix):

                text = text[len(prefix):].strip()

                lower = text.lower()

                break

        # --------------------------------------------------
        # Remove English question patterns
        # --------------------------------------------------

        for pattern in en_patterns:

            text = re.sub(
                pattern,
                "",
                text,
                flags=re.I,
            ).strip()

        # --------------------------------------------------
        # Trim punctuation
        # --------------------------------------------------

        text = text.strip(trim_chars)

        # --------------------------------------------------
        # Normalize whitespace
        # --------------------------------------------------

        text = cls._SPACE_RE.sub(
            " ",
            text,
        ).strip()

        # --------------------------------------------------
        # Limit length
        # --------------------------------------------------

        if len(text) > max_length:

            text = text[:max_length].rstrip()

        return text
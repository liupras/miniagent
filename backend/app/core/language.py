#!/usr/bin/python
# -*- coding:utf-8 -*-

"""System-wide language support and normalization rules."""

SUPPORTED_LANGUAGES = frozenset({"zh", "en"})


def normalize_language(lang: str) -> str:
    """Collapse a supported language tag to MiniAgent's base language."""
    base_language = lang.strip().replace("-", "_").split("_", 1)[0].lower()
    if base_language not in SUPPORTED_LANGUAGES:
        raise ValueError("MiniAgent only supports Chinese (zh) and English (en)")
    return base_language

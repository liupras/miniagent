#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-07
# @description: Title generator Config

from pydantic import BaseModel, Field
from functools import lru_cache
from pathlib import Path

import yaml


class LanguageRule(BaseModel):
    prefixes: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)


class ConversationTitleConfig(BaseModel):

    default_title: str = "新对话"

    max_length: int = 80

    max_title_length: int = 24

    trim_chars: str = ""

    bad_titles: list[str] = Field(default_factory=list)

    languages: dict[str, LanguageRule] = Field(default_factory=dict)

@lru_cache(maxsize=1)
def load_config() -> ConversationTitleConfig:

    path = Path(__file__).with_name(
        "conversation_title.yaml"
    )

    with path.open(
        "r",
        encoding="utf-8",
    ) as f:

        data = yaml.safe_load(f)

    return ConversationTitleConfig.model_validate(
        data
    )
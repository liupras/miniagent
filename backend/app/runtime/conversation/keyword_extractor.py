#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-07
# @description: KeywordExtractor for title

import jieba.analyse
from loguru import logger

class KeywordExtractor:

    @staticmethod
    def extract(text: str, topk: int = 4) -> str:

        try:
            keywords = jieba.analyse.extract_tags(
                text,
                topK=topk,
            )

            return " ".join(keywords)
        except Exception as e:
            logger.error(f"[KeywordExtractor]->extract:{e}")
            return ""
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-19
# @description: Preprocessing the legal text makes it easier to split the clauses later.

import re

def normalize_law_text(text: str) -> str:
    """
    Intelligent segmentation of legal provisions: Identifying independent "Article X" and skipping the citation context.
    """

    # 1. Quotation signal words (appearing before "Article X", indicating the context of the quotation, not segmented)
    CITATION_SIGNALS = (
        r"依照|根据|按照|参照|依据|遵照|遵循|"
        r"适用|援引|引用|引照|"
        r"违反|触犯|符合|满足|具备|构成|"
        r"依\s*|据\s*|按\s*|照\s*|"
        r"除|除依|除按|如未|如不|若未|若违反|"
        r"对于|关于|有关|就|"
        # 关键增加：处理“第三条、第四条”或“第三条至第五条”
        r"、|，|及|和|至|与|或" 
    )

    # 2. Chinese character prefix filtering（如“本法”、“上述”）
    PREFIX_WORDS = r"[\u4e00-\u9fa5]"

    ARTICLE = r"第\s*[一二三四五六七八九十百千万0-9]+\s*条"

    # 3. Combination Pattern
    # group(1): signal words or prefix characters
    # group(2): Target "Article X"
    pattern = re.compile(rf"({CITATION_SIGNALS}|{PREFIX_WORDS})?({ARTICLE})")

    def _replacer(m: re.Match) -> str:
        signal   = m.group(1)   # Signal word, or None if none.
        article  = m.group(2)   # Article X

        if signal:
            # Quoted context → Preserve as is, without line breaks.
            return signal + article
        else:
            # Independent clause → Insert a newline before the clause
            return "\n" + article

    text = pattern.sub(_replacer, text)

    # Clean up: Standardize line breaks and remove leading and trailing spaces.
    text = re.sub(r"\n\s*\n+", "\n", text)

    return text.strip()
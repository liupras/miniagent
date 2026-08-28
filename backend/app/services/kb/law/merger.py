#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-29
# @description: law citation merger.

from app.services.kb.citation_merger import CitationMerger
from app.services.kb.retrieval_model import RetrievedChunk

class LawMerger(CitationMerger):
    """
    Legal and regulatory merging strategy, covering the following merge steps:
    - Write chunks first (article_no and other information)
    """

    def merge(
        self,
        doc_info: dict,
        chunk: RetrievedChunk,
    ) -> dict:
        result = super().merge(doc_info, chunk)

        article_no = chunk.metadata.get("article_no", "")
        result["article_no"] = f"第{article_no}条" if article_no else ""

        return result

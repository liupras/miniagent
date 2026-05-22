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
    - Fields within DOC_AUTHORITATIVE are based on the document; others are supplemented only.
    """

    DOC_AUTHORITATIVE: frozenset[str] = frozenset({
        "title",
        "office",
        "publish_date",
        "expiry_date",
        "implement_date",
        "status",
        "type",
    })

    def merge(
        self,
        doc_info: dict,
        chunk: RetrievedChunk,
    ) -> dict:
        article_no = chunk.metadata.get("article_no","")
        article_no_str = ""
        if article_no:
            article_no_str = f"第{article_no}条"
        result: dict = {
            "doc_id":   chunk.doc_id,
            "chunk_id": chunk.chunk_id,
            "filename": doc_info.get("filename", ""),
            "article_no":article_no_str
        }

        for k, v in doc_info.items():
            if k == "filename":
                continue
            if k in self.DOC_AUTHORITATIVE:
                result[k] = v
            elif k not in result:
                result[k] = v

        return result
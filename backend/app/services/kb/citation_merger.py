#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-29
# @description: default citation merger.

from app.services.kb.retrieval_model import RetrievedChunk

class CitationMerger:
    """
    Default merge strategy:
    - doc_id / chunk_id / filename are written by system fields
    - doc field takes precedence
    - chunk field is only used to fill in gaps
    """

    def merge(
        self,
        doc_info: dict,
        chunk: RetrievedChunk,
    ) -> dict:
        result: dict = {
            "doc_id":   chunk.doc_id,
            "chunk_id": chunk.chunk_id,
            "filename": doc_info.get("filename", ""),
        }

        for k, v in doc_info.items():
            if k != "filename":
                result[k] = v

        return result
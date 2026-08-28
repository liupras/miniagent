#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-29
# @description: default citation merger.

from pathlib import Path
from typing import Optional

from app.services.kb.retrieval_model import RetrievedChunk


def source_from_filename(filename: object) -> Optional[str]:
    """Return a stable, user-facing source name without the final extension."""
    if not isinstance(filename, str) or not filename.strip():
        return None

    source = Path(filename.strip()).stem.strip()
    return source or None


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
        filename = doc_info.get("filename", "")
        result: dict = {
            "doc_id":   chunk.doc_id,
            "chunk_id": chunk.chunk_id,
            "filename": filename,
            "source":   source_from_filename(filename),
        }

        for k, v in doc_info.items():
            if k != "filename":
                result[k] = v

        return result

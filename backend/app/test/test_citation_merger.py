from types import SimpleNamespace

import pytest

from app.services.kb.citation_merger import CitationMerger, source_from_filename
from app.services.kb.law.merger import LawMerger


def _chunk(*, article_no=None):
    metadata = {}
    if article_no is not None:
        metadata["article_no"] = article_no
    return SimpleNamespace(doc_id=7, chunk_id=11, metadata=metadata)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("公司法.txt", "公司法"),
        ("公司法.2024修订.pdf", "公司法.2024修订"),
        ("知识产权法", "知识产权法"),
        ("  著作权法.docx  ", "著作权法"),
        ("", None),
        (None, None),
    ],
)
def test_source_from_filename(filename, expected):
    assert source_from_filename(filename) == expected


def test_default_citation_contains_source_but_not_article_number():
    result = CitationMerger().merge(
        {"filename": "产品说明书.pdf"},
        _chunk(article_no="十"),
    )

    assert result["source"] == "产品说明书"
    assert "article_no" not in result


def test_law_citation_contains_source_and_formatted_article_number():
    result = LawMerger().merge(
        {
            "filename": "中华人民共和国著作权法.txt",
            "title": "中华人民共和国著作权法",
            "type": "法律",
        },
        _chunk(article_no="十"),
    )

    assert result["source"] == "中华人民共和国著作权法"
    assert result["article_no"] == "第十条"
    assert result["title"] == "中华人民共和国著作权法"


def test_law_citation_keeps_chunk_article_number_authoritative():
    result = LawMerger().merge(
        {
            "filename": "中华人民共和国著作权法.txt",
            "article_no": "文档级错误值",
        },
        _chunk(article_no="十二"),
    )

    assert result["article_no"] == "第十二条"


def test_law_citation_has_empty_article_number_when_not_detected():
    result = LawMerger().merge(
        {"filename": "法律前言.txt"},
        _chunk(),
    )

    assert result["source"] == "法律前言"
    assert result["article_no"] == ""

from types import SimpleNamespace

import pytest

from app.runtime.agent.tool_builder import _get_chunk_source


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({"citation": {"filename": "公司法.txt"}}, "公司法"),
        ({"citation": {"filename": "公司法.2024修订.pdf"}}, "公司法.2024修订"),
        ({"citation": {"filename": "知识产权法"}}, "知识产权法"),
        ({"citation": {"filename": "  著作权法.docx  "}}, "著作权法"),
        ({"citation": {"filename": ""}}, None),
        ({"citation": {}}, None),
        ({}, None),
        (None, None),
    ],
)
def test_get_chunk_source(metadata, expected):
    chunk = SimpleNamespace(metadata=metadata)

    assert _get_chunk_source(chunk) == expected


def test_get_chunk_source_without_metadata_attribute():
    assert _get_chunk_source(SimpleNamespace()) is None

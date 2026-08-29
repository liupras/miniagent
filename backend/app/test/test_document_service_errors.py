import asyncio

import pytest

from app.core.i18n import error_translation
from app.services.kb.exceptions import (
    DocumentDeletionError,
    DocumentIndexingError,
)
from app.services.kb.service_document import (
    DocumentEmptyDataError,
    KBDocumentService,
)


class _DocumentDatabase:
    def __init__(self):
        self.status_calls = []

    async def mark_status(self, *args, **kwargs):
        self.status_calls.append((args, kwargs))


def _service():
    service = object.__new__(KBDocumentService)
    service.doc_db = _DocumentDatabase()
    return service


def _translations(key, **params):
    values = {
        "document.indexing_failed": "文档索引失败",
        "document.deletion_failed": "文档删除失败",
        "document.empty_data": "没有可索引的数据块",
        "progress.stage.error": "错误",
    }
    return values.get(key, key).format(**params)


def test_unexpected_document_failure_separates_diagnostics_from_public_text(
    monkeypatch,
):
    monkeypatch.setattr(error_translation, "t", _translations)
    service = _service()
    events = []

    async def emit(*args, **kwargs):
        events.append((args, kwargs))

    source_error = RuntimeError("private vector database endpoint detail")
    error = asyncio.run(
        service._record_document_failure(
            doc_id=7,
            exc=source_error,
            error_type=DocumentIndexingError,
            emit=emit,
            persist_failed_status=True,
        )
    )

    assert isinstance(error, DocumentIndexingError)
    assert error.cause is source_error
    assert service.doc_db.status_calls[0][1]["error_message"] == "文档索引失败"
    assert events[0][0][1] == "文档索引失败"
    assert "private vector database" not in str(service.doc_db.status_calls)
    assert "private vector database" not in str(events)


def test_existing_document_domain_error_is_preserved(monkeypatch):
    monkeypatch.setattr(error_translation, "t", _translations)
    service = _service()
    events = []

    async def emit(*args, **kwargs):
        events.append((args, kwargs))

    source_error = DocumentEmptyDataError(7)
    error = asyncio.run(
        service._record_document_failure(
            doc_id=7,
            exc=source_error,
            error_type=DocumentIndexingError,
            emit=emit,
            persist_failed_status=True,
        )
    )

    assert error is source_error
    assert service.doc_db.status_calls[0][1]["error_message"] == "没有可索引的数据块"
    assert events[0][0][1] == "没有可索引的数据块"


def test_delete_failure_does_not_overwrite_document_status(monkeypatch):
    monkeypatch.setattr(error_translation, "t", _translations)
    service = _service()

    async def emit(*args, **kwargs):
        pass

    error = asyncio.run(
        service._record_document_failure(
            doc_id=7,
            exc=RuntimeError("private storage detail"),
            error_type=DocumentDeletionError,
            emit=emit,
            persist_failed_status=False,
        )
    )

    assert isinstance(error, DocumentDeletionError)
    assert service.doc_db.status_calls == []

import asyncio

import duckdb
import pytest

from app.schemas.exceptions import BaseDomainError
from app.services.sql_agent.exceptions import (
    SQLTableImportError,
    SQLTableNotFoundError,
    SQLTableOperationError,
    SQLUnsupportedFileTypeError,
)
from app.services.sql_agent.service import SQLAgentService


class _Manager:
    def __init__(self):
        self.error = None
        self.columns = []
        self.preview = {}
        self.deleted = True
        self.import_kwargs = None

    def import_table(self, **kwargs):
        self.import_kwargs = kwargs
        if self.error:
            raise self.error
        return {"table_path": '"main"."orders"', "row_count": 3}

    def list_schemas(self):
        if self.error:
            raise self.error
        return []

    def get_table_columns(self, *_args):
        return self.columns

    def preview_table(self, **_kwargs):
        return self.preview

    def drop_table(self, *_args):
        return self.deleted


def _service(manager=None):
    service = object.__new__(SQLAgentService)
    service._db_manager = manager or _Manager()
    return service


def _import(service, filename="orders.csv"):
    return asyncio.run(
        service.import_table(
            file_path="temporary-upload",
            source_filename=filename,
            schema_name="main",
            table_name=None,
            sheet_name=None,
            primary_key=None,
            force_cast=False,
            allow_new_columns=False,
        )
    )


def test_import_classification_and_default_table_name_are_service_logic():
    manager = _Manager()
    result = _import(_service(manager))

    assert result["file_type"] == "csv"
    assert result["table_name"] == "orders"
    assert manager.import_kwargs["file_type"] == "csv"
    assert manager.import_kwargs["table_name"] == "orders"
    assert SQLAgentService.classify_import_file("book.xlsx") == "excel"


def test_unsupported_import_file_is_a_domain_error():
    with pytest.raises(SQLUnsupportedFileTypeError) as captured:
        SQLAgentService.classify_import_file("orders.pdf")

    assert isinstance(captured.value, BaseDomainError)
    assert captured.value.i18n_key() == "sql_agent.unsupported_file_extension"


def test_predictable_import_validation_failure_is_converted():
    manager = _Manager()
    manager.error = ValueError("missing primary key")

    with pytest.raises(SQLTableImportError) as captured:
        _import(_service(manager))

    assert captured.value.__cause__ is manager.error


def test_duckdb_import_failure_is_converted_to_operation_error():
    manager = _Manager()
    manager.error = duckdb.Error("database unavailable")

    with pytest.raises(SQLTableOperationError) as captured:
        _import(_service(manager))

    assert captured.value.operation == "import"
    assert captured.value.__cause__ is manager.error


def test_table_not_found_is_raised_by_service():
    manager = _Manager()
    manager.columns = None
    manager.preview = None
    manager.deleted = False
    service = _service(manager)

    operations = (
        lambda: service.get_table_columns("main", "missing"),
        lambda: service.preview_table("main", "missing", 1, 20),
        lambda: service.drop_table("main", "missing"),
    )
    for operation in operations:
        with pytest.raises(SQLTableNotFoundError):
            asyncio.run(operation())


def test_duckdb_browsing_failure_is_converted():
    manager = _Manager()
    manager.error = duckdb.Error("database unavailable")

    with pytest.raises(SQLTableOperationError) as captured:
        asyncio.run(_service(manager).list_schemas())

    assert captured.value.operation == "list_schemas"

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description:  Stable application errors for SQL Agent table management.

from app.schemas.exceptions import (
    BaseDomainError,
    InfrastructureError,
    NotFoundError,
    UnsupportedMediaTypeError,
)


class SQLTableNotFoundError(NotFoundError):
    def __init__(self, schema_name: str, table_name: str) -> None:
        self.schema_name = schema_name
        self.table_name = table_name
        super().__init__("SQLTable", f"{schema_name}.{table_name}")


class SQLUnsupportedFileTypeError(UnsupportedMediaTypeError):
    error_key = "sql_agent.unsupported_file_extension"

    def __init__(self, filename: str, allowed: str) -> None:
        self.filename = filename
        super().__init__(
            f"Unsupported SQL table import file: {filename}",
            params={"filename": filename, "allowed": allowed},
        )


class SQLTableImportError(BaseDomainError):
    error_key = "sql_agent.import_failed"

    def __init__(
        self,
        filename: str,
        *,
        cause: BaseException | None = None,
    ) -> None:
        self.filename = filename
        super().__init__(
            message=f"SQL table import validation failed for '{filename}'",
            params={"filename": filename},
            cause=cause,
        )


class SQLTableOperationError(InfrastructureError):
    error_key = "sql_agent.operation_failed"

    def __init__(
        self,
        operation: str,
        *,
        cause: BaseException | None = None,
    ) -> None:
        self.operation = operation
        super().__init__(
            f"SQL table operation failed: {operation}",
            params={"operation": operation},
            cause=cause,
        )

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-23
# @description: Data Contract for SQL Agent

from typing import Any, Optional

from pydantic import BaseModel, Field

class ImportTableResponse(BaseModel):
    """Result of a table import operation (CSV or Excel)."""

    table_path: str = Field(
        ...,
        description='Fully-qualified table path created or updated, e.g. "main"."sales_tbl".',
    )
    schema_name: str
    table_name: Optional[str]
    row_count: Optional[int] = Field(
        default=None, description="Number of rows written to the target table."
    )
    file_type: str = Field(..., description='"csv" or "excel".')
    sheet_name: Optional[str] = Field(
        default=None, description="Sheet imported, when the source file was Excel."
    )


class SchemaInfo(BaseModel):
    schema_name: str
    table_count: int = 0


class TableInfo(BaseModel):
    schema_name: str
    table_name: str
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    comment: Optional[str] = None


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool = True
    is_primary_key: bool = False
    default: Optional[str] = None


class TablePreviewResponse(BaseModel):
    columns: list[ColumnInfo]
    rows: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
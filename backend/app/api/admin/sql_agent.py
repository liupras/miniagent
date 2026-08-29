#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-03 (updated 2026-07-06)
# @description: FastAPI router — SQL Agent / Table Management endpoints

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile

from app.core.logger_config import get_logger

logger = get_logger(__name__)
from app.schemas.common import ApiResponse
from app.core.i18n.i18n import t

from app.schemas.admin.sql_agent import ImportTableResponse,SchemaInfo,TableInfo,ColumnInfo,TablePreviewResponse

router = APIRouter()

# ═══════════════════════════════════════════════════════════════════════════
# Dependency helpers
# ═══════════════════════════════════════════════════════════════════════════

def _get_service(request: Request):
    """
    Pull SQLAgentService from the application state.
    """
    return request.app.state.container.sql_agent_service

from app.core.security.auth_permission import AuthPermission
_list   = AuthPermission.Permission("table:list")
_add    = AuthPermission.Permission("table:add")
_delete = AuthPermission.Permission("table:delete")

# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

# Loosely-checked content types. Browsers/clients are inconsistent about
# what they send for CSV/Excel, so we mostly rely on the file extension
# and only use content_type to reject obviously-wrong uploads.
ACCEPTED_CONTENT_TYPES = {
    "text/csv",
    "text/plain",
    "application/csv",
    "text/tab-separated-values",
    "application/vnd.ms-excel",  # .xls
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/octet-stream",  # generic fallback used by many clients
}


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints — Import
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/import",
    response_model=ApiResponse,
    summary="Import a CSV or Excel file into DuckDB",
    description=(
        "Upload a CSV or Excel (.xlsx/.xls) file and import it into the specified "
        "DuckDB schema/table. Supports automatic schema creation, UPSERT on primary "
        "key, type promotion, and optional new-column expansion. File type is "
        "detected automatically from the extension. For Excel files with multiple "
        "sheets, pass `sheet_name` to select one (defaults to the first sheet)."
    ),
)
async def import_table(
    file: UploadFile = File(..., description="CSV or Excel file to import."),
    schema_name: str = Form(
        default="main",
        pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$",
        description="Target DuckDB schema (default: 'main').",
        examples=["main"],
    ),
    table_name: Optional[str] = Form(
        default=None,
        pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$",
        description="Target table name. Derived from the filename when omitted.",
        examples=["orders"],
    ),
    sheet_name: Optional[str] = Form(
        default=None,
        description=(
            "Excel sheet to import (by name). Ignored for CSV files. "
            "Defaults to the first sheet when omitted."
        ),
    ),
    primary_key: Optional[str] = Form(
        default=None,
        description=(
            "Column(s) name used for UPSERT conflict resolution. Please separate "
            "multiple values with commas. When omitted, rows are appended "
            "(may produce duplicates)."
        ),
    ),
    force_cast: bool = Form(
        default=False,
        description="When True, silently cast type-mismatched columns.",
    ),
    allow_new_columns: bool = Form(
        default=False,
        description="When True, add columns present in the file but absent from the existing table.",
    ),
    service=Depends(_get_service),
    caller_id: int            = Depends(_add),
) -> ApiResponse:
    """
    Accept a multipart CSV/Excel upload and import it into DuckDB.

    Flow
    ────
    1. Validate the extension is one we support (csv/tsv/txt or xlsx/xls/xlsm).
    2. Stream the uploaded file to a secure temporary file on disk.
    3. Delegate to ``SQLAgentService.import_table`` (→ ``DBManager.import_table``),
       which dispatches internally to a CSV or Excel reader based on ``file_type``.
    4. Delete the temporary file regardless of success or failure.
    5. Return the fully-qualified table path.
    """
    source_filename = file.filename or ""
    file_type = service.classify_import_file(source_filename)

    if file.content_type and file.content_type not in ACCEPTED_CONTENT_TYPES:
        # Content-type is only a soft signal (many uploaders send generic/incorrect
        # values), so we log rather than reject once the extension already passed.
        logger.warning(
            f"Unexpected content_type '{file.content_type}' for import "
            f"of '{file.filename}' (accepted based on extension: {file_type})"
        )

    suffix = os.path.splitext(file.filename or "upload")[1] or (
        ".csv" if file_type == "csv" else ".xlsx"
    )
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        result = await service.import_table(
            file_path=tmp_path,
            source_filename=source_filename,
            schema_name=schema_name,
            table_name=table_name,
            sheet_name=sheet_name,
            primary_key=primary_key,
            force_cast=force_cast,
            allow_new_columns=allow_new_columns,
        )
    finally:
        # Always clean up the temporary file
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError as exc:
            logger.warning("Failed to remove upload temp file '{}': {}", tmp_path, exc)
        try:
            await file.close()
        except Exception as exc:
            logger.warning("Failed to close uploaded file '{}': {}", source_filename, exc)

    data = ImportTableResponse.model_validate(result)
    return ApiResponse(data=data)


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints — Schema / Table browsing
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/schemas",
    response_model=ApiResponse,
    summary="List DuckDB schemas",
)
async def list_schemas(
    service=Depends(_get_service),
    caller_id: int            = Depends(_list),
) -> ApiResponse:
    schemas = await service.list_schemas()
    return ApiResponse(data=[SchemaInfo(**s) for s in schemas])


@router.get(
    "/tables",
    response_model=ApiResponse,
    summary="List tables within a schema",
)
async def list_tables(
    schema_name: str = Query(default="main"),
    service=Depends(_get_service),
    caller_id: int            = Depends(_list),
) -> ApiResponse:
    tables = await service.list_tables(schema_name=schema_name)
    return ApiResponse(data=[TableInfo(**tbl) for tbl in tables])


@router.get(
    "/tables/{schema_name}/{table_name}/columns",
    response_model=ApiResponse,
    summary="Get column definitions for a table",
)
async def get_table_columns(
    schema_name: str,
    table_name: str,
    service=Depends(_get_service),
    caller_id: int            = Depends(_list),
) -> ApiResponse:
    columns = await service.get_table_columns(
        schema_name=schema_name,
        table_name=table_name,
    )
    return ApiResponse(data=[ColumnInfo(**c) for c in columns])


@router.get(
    "/tables/{schema_name}/{table_name}/data",
    response_model=ApiResponse,
    summary="Preview paginated table data",
)
async def get_table_data(
    schema_name: str,
    table_name: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    order_by: Optional[str] = Query(default=None),
    order_desc: bool = Query(default=False),
    service=Depends(_get_service),
    caller_id: int            = Depends(_list),
) -> ApiResponse:
    preview = await service.preview_table(
        schema_name=schema_name,
        table_name=table_name,
        page=page,
        page_size=page_size,
        order_by=order_by,
        order_desc=order_desc,
    )
    return ApiResponse(
        data=TablePreviewResponse(
            columns=[ColumnInfo(**c) for c in preview["columns"]],
            rows=preview["rows"],
            total=preview["total"],
            page=page,
            page_size=page_size,
        )
    )


@router.delete(
    "/tables/{schema_name}/{table_name}",
    response_model=ApiResponse,
    summary="Drop a table",
)
async def delete_table(
    schema_name: str,
    table_name: str,
    service=Depends(_get_service),
    caller_id: int            = Depends(_delete),
) -> ApiResponse:
    await service.drop_table(schema_name=schema_name, table_name=table_name)
    return ApiResponse(
        message=t(
            "sql_agent.delete_success", schema_name=schema_name, table_name=table_name
        )
    )

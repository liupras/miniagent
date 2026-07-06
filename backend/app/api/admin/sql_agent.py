#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-03
# @description: FastAPI router — SQL Agent endpoints

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field

from loguru import logger

from app.schemas.common import ApiResponse
from app.core.i18n.i18n import t

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════
# Dependency helpers
# ═══════════════════════════════════════════════════════════════════════════

def _get_service(request: Request):
    """
    Pull SQLAgentService from the application state.
    """
    return request.app.state.container.sql_agent_service


# ═══════════════════════════════════════════════════════════════════════════
# Request / Response schemas
# ═══════════════════════════════════════════════════════════════════════════

class ImportCsvResponse(BaseModel):
    """Result of a CSV import operation."""

    table_path: str = Field(
        ...,
        description='Fully-qualified table path created or updated, e.g. "main"."sales_tbl".',
    )
    schema_name: str
    table_name: Optional[str]

# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/import-csv",
    response_model=ApiResponse,
    summary="Import a CSV file into DuckDB",
    description=(
        "Upload a CSV file and import it into the specified DuckDB schema/table. "
        "Supports automatic schema creation, UPSERT on primary key, type promotion, "
        "and optional new-column expansion. "
        "The uploaded file is written to a temporary path and cleaned up after import."
    ),
)
async def import_csv(
    file: UploadFile = File(..., description="CSV file to import."),
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
        examples=["orders"]
    ),
    primary_key: Optional[str] = Form(
        default=None,
        description=(
            "Column(s) name used for UPSERT conflict resolution. Please separate multiple values ​​with commas."
            "When omitted, rows are appended (may produce duplicates)."
        )
    ),
    force_cast: bool = Form(
        default=False,
        description="When True, silently cast type-mismatched columns.",
    ),
    allow_new_columns: bool = Form(
        default=False,
        description="When True, add CSV columns absent from the existing table.",
    ),
    service=Depends(_get_service),
) -> ApiResponse:
    """
    Accept a multipart CSV upload and import it into DuckDB.

    Flow
    ────
    1. Stream the uploaded file to a secure temporary file on disk.
    2. Delegate to ``SQLAgentService.import_csv`` (→ ``DBManager.import_csv``).
    3. Delete the temporary file regardless of success or failure.
    4. Return the fully-qualified table path.
    """
    # Validate content type loosely — accept text/csv and application/octet-stream
    if file.content_type and file.content_type not in (
        "text/csv",
        "text/plain",
        "application/csv",
        "application/octet-stream",
    ):
        return ApiResponse(code=415,message=t("common.error_415",content_type=file.content_type))

    # Write upload to a temp file so DBManager (pandas) can read it from disk
    suffix = os.path.splitext(file.filename or "upload")[1] or ".csv"
    if not table_name:
        # Prevent temporary filename from becoming table name
        table_name = os.path.splitext(file.filename)[0]
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        table_path = await service.import_csv(
            file_path=tmp_path,
            schema_name=schema_name,
            table_name=table_name,
            primary_key=primary_key,
            force_cast=force_cast,
            allow_new_columns=allow_new_columns,
        )
    except Exception as exc:
        logger.error(f"CSV import failed: {exc}")
        return ApiResponse(code=500,message=t("common.error_500"))
    finally:
        # Always clean up the temporary file
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        await file.close()

    data = ImportCsvResponse(
        table_path=table_path,
        schema_name=schema_name,
        table_name=table_name,
    )
    return ApiResponse(data=data)


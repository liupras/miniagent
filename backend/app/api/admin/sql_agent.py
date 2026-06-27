#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-03
# @description: FastAPI router — SQL Agent endpoints

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

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


class CacheInfoResponse(BaseModel):
    """Current agent cache state."""

    cache: Dict[str, Any]


class InvalidateCacheRequest(BaseModel):
    """Optional body for targeted cache eviction."""

    llm_provider_id: Optional[int] = Field(
        default=None,
        description="Evict only agents for this LLM provider. "
                    "Omit to evict ALL cached agents.",
    )
    schema_name: Optional[str] = Field(
        default="main",
        description="Schema name to evict (used together with llm_provider_id).",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/import-csv",
    response_model=ImportCsvResponse,
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
) -> ImportCsvResponse:
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
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type '{file.content_type}'. Expected a CSV file.",
        )

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
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"CSV import failed: {exc}",
        )
    finally:
        # Always clean up the temporary file
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        await file.close()

    return ImportCsvResponse(
        table_path=table_path,
        schema_name=schema_name,
        table_name=table_name,
    )


@router.get(
    "/cache",
    response_model=CacheInfoResponse,
    summary="Inspect the agent cache",
    description="Returns the set of (llm_provider_id, schema_name) pairs currently cached.",
)
async def cache_info(service=Depends(_get_service)) -> CacheInfoResponse:
    return CacheInfoResponse(cache=service.cache_info())


@router.post(
    "/cache/invalidate",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Invalidate cached agents",
    description=(
        "Evict one agent (when llm_provider_id is provided) or ALL cached agents "
        "(when the body is empty or llm_provider_id is omitted). "
        "Use after updating LLM configs or prompt templates."
    ),
)
async def invalidate_cache(
    body: InvalidateCacheRequest = InvalidateCacheRequest(),
    service=Depends(_get_service),
) -> None:
    if body.llm_provider_id is not None:
        service.invalidate(
            llm_provider_id=body.llm_provider_id,
            schema_name=body.schema_name or "main",
        )
    else:
        service.invalidate_all()

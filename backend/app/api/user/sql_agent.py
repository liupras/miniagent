#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-03
# @description: FastAPI router — SQL Agent endpoints

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.schemas.user.sql_agent import QueryRequest
from app.schemas.common import ApiResponse

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
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/query",
    response_model=ApiResponse,
    summary="Run a natural-language data query",
    description=(
        "Submit a natural-language question. The SQL Agent will autonomously "
        "inspect the database schema, generate SQL or Python analysis code, "
        "execute it against DuckDB, and return a human-readable answer."
    ),
)
async def query(
    body: QueryRequest,
    service=Depends(_get_service),
) -> ApiResponse:
    """
    Execute a natural-language query via SQLAgentService.

    The agent may perform multiple internal tool-call rounds (schema lookup →
    SQL generation → execution) before producing its final answer.
    """
    
    answer = await service.run(
        user_query=body.query,
        tool_name=body.tool_name,        
    )

    return ApiResponse(data=answer)

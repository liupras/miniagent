#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-03
# @description: FastAPI router — SQL Agent endpoints

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from app.core.i18n.i18n import t
from app.core.logger_config import get_logger
from app.schemas.common import ApiResponse
from app.schemas.user.sql_agent import QueryRequest


logger = get_logger(__name__)

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

@router.get("/chat_stream")
async def chat_stream(
    query: str = Query(..., description="User data question"), 
    service=Depends(_get_service),
):
    """
    The Agent's thought process and execution trajectory are pushed to the front end in real time via the SSE (Server-Sent Events) protocol.
    """
    async def event_generator():
        try:            
            async for event in service.astream(user_query=query):                
                yield f"event: {event['event']}\n"
                yield f"data: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
                
                # Forcefully flush to the buffer to ensure real-time performance.
                await asyncio.sleep(0)
                
        except asyncio.CancelledError:
            # Preserve cancellation semantics so upstream resources can stop.
            raise
        except Exception as exc:
            # The response has already started, so the global FastAPI
            # exception handler cannot replace it with an HTTP response.
            # Keep diagnostics server-side and expose only a stable SSE error.
            logger.exception("SQL Agent stream failed: {}", exc)
            payload = {
                "event": "error",
                "code": "SQL_AGENT_STREAM_FAILED",
                "message": t("sql_agent.stream_failed"),
            }
            yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

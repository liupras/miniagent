#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-03
# @description: FastAPI router — SQL Agent endpoints

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════
# Dependency helpers
# ═══════════════════════════════════════════════════════════════════════════

def _get_service(request: Request):
    """
    Pull SQLAgentService from the application state.

    Assumes the service was registered at startup:
        app.state.container = container          # ServiceContainer instance
    """
    container = request.app.state.container
    service = getattr(container, "sql_agent_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SQLAgentService is not registered in ServiceContainer.",
        )
    return service


# ═══════════════════════════════════════════════════════════════════════════
# Request / Response schemas
# ═══════════════════════════════════════════════════════════════════════════

class QueryRequest(BaseModel):
    """Payload for a natural-language data query."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Natural-language question to answer against the database.",
        examples=["What are the sales figures for each country?"],
    )
    llm_provider_id: int = Field(
        default=1,
        ge=1,
        description="ID of the LLM provider row to use for this request.",
    )
    schema_name: str = Field(
        default="main",
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$",
        description="DuckDB schema the agent should query (default: 'main').",
    )


class QueryResponse(BaseModel):
    """Successful query response."""

    answer: str = Field(..., description="Natural-language answer from the agent.")
    llm_provider_id: int
    schema_name: str

# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/query",
    response_model=QueryResponse,
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
) -> QueryResponse:
    """
    Execute a natural-language query via SQLAgentService.

    The agent may perform multiple internal tool-call rounds (schema lookup →
    SQL generation → execution) before producing its final answer.
    """
    try:
        answer = await service.run(
            user_query=body.query,
            llm_provider_id=body.llm_provider_id,
            schema_name=body.schema_name,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent execution failed: {exc}",
        )

    return QueryResponse(
        answer=answer,
        llm_provider_id=body.llm_provider_id,
        schema_name=body.schema_name,
    )

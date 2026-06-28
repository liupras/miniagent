#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-28
# @description: Data Contract for sql agent

from pydantic import BaseModel, Field


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
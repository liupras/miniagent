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
    tool_name: str = Field(
        default="sql_agent",
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$",
        description="Name of the tool to use (default: 'sql_agent').",
    )
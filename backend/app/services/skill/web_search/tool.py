#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-27
# @description: web_search tool call.

from __future__ import annotations
from typing import Callable

def web_search(container,tool_name) -> Callable:
    """
    The factory function, callable_path = "app.services.skill.web_search.tool:web_search", 
    is called by tool_builder when the signature contains the agent parameter.
    """
    async def _search(query: str) -> str:
        state = await container.web_search_service.search(
            tool_name=tool_name,
            query=query,           
        )
        from app.services.skill.web_search import WebSearchPipeline
        return WebSearchPipeline.format_for_llm(state)

    return _search
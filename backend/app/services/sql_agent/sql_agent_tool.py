#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-05
# @description: sql agent tool call.

from __future__ import annotations
from typing import Callable

def run(container,tool_name) -> Callable:
    """
    The factory function, callable_path = "sql_agent.sql_agent_tool:run", 
    is called by tool_builder when the signature contains the agent parameter.
    """
    async def _run(query: str) -> str:
        result = await container.sql_agent_service.run(
            tool_name=tool_name,            
            user_query=query,            
        )
        
        return result

    return _run
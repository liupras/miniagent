#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-10
# @description: Stable application exceptions raised by the agent runtime.

from app.schemas.exceptions import InfrastructureError, NotFoundError


class ToolNotRegisteredError(NotFoundError):
    """The model requested a tool that is not registered for this agent."""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__("Tool", tool_name)


class ToolExecutionError(InfrastructureError):
    """An unexpected failure occurred inside a registered tool."""

    error_key = "tool.execution_failed"

    def __init__(
        self,
        tool_name: str,
        *,
        cause: BaseException | None = None,
    ) -> None:
        self.tool_name = tool_name
        super().__init__(
            f"Tool '{tool_name}' execution failed",
            params={"name": tool_name},
            cause=cause,
        )

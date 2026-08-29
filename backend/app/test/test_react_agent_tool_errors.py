#!/usr/bin/python
# -*- coding:utf-8 -*-

import asyncio

import pytest
from langchain_core.tools import BaseTool

from app.runtime.agent.exceptions import ToolExecutionError, ToolNotRegisteredError
from app.runtime.agent.react_agent import ToolReActAgent
from app.schemas.exceptions import ToolInactiveError


class _FailingTool(BaseTool):
    name: str = "failing_tool"
    description: str = "A tool used to verify exception propagation."
    error: BaseException

    def _run(self, query: str) -> str:
        raise self.error

    async def _arun(self, query: str) -> str:
        raise self.error


class _ToolCallingLLM:
    def __init__(self) -> None:
        self.call_count = 0

    async def achat(self, messages, tool_schema=None):
        self.call_count += 1
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "failing_tool",
                        "arguments": {"query": "x"},
                    },
                }
            ],
        }


def _agent_with(tool: BaseTool) -> ToolReActAgent:
    return ToolReActAgent(agent_llm=None, tools=[tool])


def test_async_tool_preserves_domain_error():
    error = ToolInactiveError("failing_tool")
    agent = _agent_with(_FailingTool(error=error))

    with pytest.raises(ToolInactiveError) as caught:
        asyncio.run(agent._execute_tool_async("failing_tool", {"query": "x"}))

    assert caught.value is error


def test_sync_tool_preserves_domain_error():
    error = ToolInactiveError("failing_tool")
    agent = _agent_with(_FailingTool(error=error))

    with pytest.raises(ToolInactiveError) as caught:
        agent._execute_tool_sync("failing_tool", {"query": "x"})

    assert caught.value is error


def test_async_tool_wraps_unexpected_error_without_exposing_detail():
    error = RuntimeError("private provider detail")
    agent = _agent_with(_FailingTool(error=error))

    with pytest.raises(ToolExecutionError) as caught:
        asyncio.run(agent._execute_tool_async("failing_tool", {"query": "x"}))

    assert caught.value.cause is error
    assert caught.value.__cause__ is error
    assert "private provider detail" not in caught.value.to_detail()


def test_sync_tool_wraps_unexpected_error_without_exposing_detail():
    error = RuntimeError("private provider detail")
    agent = _agent_with(_FailingTool(error=error))

    with pytest.raises(ToolExecutionError) as caught:
        agent._execute_tool_sync("failing_tool", {"query": "x"})

    assert caught.value.cause is error
    assert caught.value.__cause__ is error
    assert "private provider detail" not in caught.value.to_detail()


def test_missing_tool_raises_instead_of_becoming_an_observation():
    agent = ToolReActAgent(agent_llm=None, tools=[])

    with pytest.raises(ToolNotRegisteredError):
        asyncio.run(agent._execute_tool_async("missing_tool", {}))

    with pytest.raises(ToolNotRegisteredError):
        agent._execute_tool_sync("missing_tool", {})


def test_async_tool_does_not_swallow_cancellation():
    agent = _agent_with(_FailingTool(error=asyncio.CancelledError()))

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(agent._execute_tool_async("failing_tool", {"query": "x"}))


def test_react_loop_stops_after_tool_execution_failure():
    llm = _ToolCallingLLM()
    agent = ToolReActAgent(
        agent_llm=llm,
        tools=[_FailingTool(error=RuntimeError("provider failed"))],
    )

    with pytest.raises(ToolExecutionError):
        asyncio.run(agent.ainvoke({"messages": [{"role": "user", "content": "go"}]}))

    assert llm.call_count == 1

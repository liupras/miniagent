#!/usr/bin/python
# -*- coding:utf-8 -*-

import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

from langchain_core.tools import BaseTool

from app.runtime.agent.react_agent import ToolReActAgent
from app.runtime.conversation.service_conversation import calculate_input_budget
from app.runtime.llm.agent_client import AgentLLM
from app.utils.tokens import TokenCounter


class _LargeObservationTool(BaseTool):
    name: str = "large_observation"
    description: str = "Return a deliberately large observation for context tests."

    def _run(self, query: str) -> str:
        return "observation-" * 300

    async def _arun(self, query: str) -> str:
        return self._run(query)


class _LoopLLMClient:
    max_output_tokens = 100

    def __init__(self):
        self.payloads = []

    async def achat(self, model, messages, **kwargs):
        self.payloads.append(deepcopy(messages))
        call_number = len(self.payloads)
        if call_number < 10:
            content = json.dumps({
                "tool_calls": [
                    {
                        "id": f"call_{call_number}",
                        "type": "function",
                        "function": {
                            "name": "large_observation",
                            "arguments": {"query": f"round {call_number}"},
                        },
                    }
                ]
            })
        else:
            content = "final answer"
        return SimpleNamespace(content=content)


def _assert_tool_messages_are_paired(messages):
    pending_call_ids = set()
    for message in messages:
        if message.get("role") == "assistant":
            assert not pending_call_ids
            pending_call_ids = {
                call.get("id")
                for call in message.get("tool_calls", [])
            }
        elif message.get("role") == "tool":
            tool_call_id = message.get("tool_call_id")
            assert tool_call_id in pending_call_ids
            pending_call_ids.remove(tool_call_id)
        elif message.get("role") == "user":
            assert not pending_call_ids
    assert not pending_call_ids


def test_ten_round_react_loop_keeps_every_provider_payload_within_budget():
    context_window_tokens = 1800
    max_output_tokens = 100
    input_budget = calculate_input_budget(
        context_window_tokens,
        max_output_tokens,
    )
    counter = TokenCounter(
        model="test-model",
        enable_exact_near_limit=False,
    )
    client = _LoopLLMClient()
    agent_llm = AgentLLM(
        client=client,
        model="test-model",
        context_window_tokens=context_window_tokens,
        max_output_tokens=max_output_tokens,
        token_counter=counter,
    )
    agent = ToolReActAgent(
        agent_llm=agent_llm,
        tools=[_LargeObservationTool()],
        system_instruction="You are a test agent.",
    )

    result = asyncio.run(agent.ainvoke({
        "messages": [{"role": "user", "content": "start"}],
    }))

    assert len(client.payloads) == 10
    assert result["messages"][-1]["content"] == "final answer"
    for payload in client.payloads:
        assert counter.count_messages(payload) <= input_budget
        assert all(
            not any(str(key).startswith("_") for key in message)
            for message in payload
        )
        _assert_tool_messages_are_paired(payload)

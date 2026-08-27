#!/usr/bin/python
# -*- coding:utf-8 -*-

import asyncio
import json
from types import SimpleNamespace

from app.runtime.agent.agent_runner import AgentRunner


class _FakeConversationService:
    def __init__(self):
        self.saved_messages = []

    async def build_messages(self, **kwargs):
        return [{"role": "user", "content": kwargs["query"]}]

    async def save_message(self, **kwargs):
        self.saved_messages.append(kwargs)


class _FakeAgent:
    # AgentRunner uses this marker to normalize messages for ToolReActAgent.
    agent_llm = object()

    async def astream(self, input):
        messages = list(input["messages"])
        messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "china_legal_kb_router",
                    "arguments": {"query": "有限责任公司最少股东人数"},
                },
            }],
        })
        yield {"messages": list(messages)}

        raw_observation = json.dumps({
            "confidence": "high",
            "chunks": [{"text": "工具内部证据", "score": 0.95}],
        }, ensure_ascii=False)
        messages.append({
            "role": "tool",
            "tool_call_id": "call_1",
            "name": "china_legal_kb_router",
            "content": raw_observation,
        })
        yield {"messages": list(messages)}

        messages.append({
            "role": "assistant",
            "content": "有限责任公司最少可以有一名股东。",
        })
        yield {"messages": list(messages)}


def test_stream_hides_tool_observation_and_persists_only_final_answer():
    conversation_service = _FakeConversationService()
    runner = AgentRunner(
        agent_id=1,
        agent_name="law_assistant",
        agent=_FakeAgent(),
        system_prompt="test",
        chat_service=conversation_service,
        llm_config=SimpleNamespace(
            context_window_tokens=4096,
            max_output_tokens=512,
            model_name="test-model",
            temperature=0.1,
        ),
    )

    async def collect_events():
        return [
            json.loads(event)
            async for event in runner.stream(
                "有限责任公司应该最少有几个股东？",
                user_id="user-1",
                session_id="session-1",
            )
        ]

    events = asyncio.run(collect_events())

    assert events == [
        {"event": "tool_start", "tools": ["china_legal_kb_router"]},
        {"event": "text", "chunk": "有限责任公司最少可以有一名股东。"},
    ]
    assert [message["role"] for message in conversation_service.saved_messages] == [
        "user",
        "assistant",
    ]
    assert conversation_service.saved_messages[-1]["content"] == (
        "有限责任公司最少可以有一名股东。"
    )

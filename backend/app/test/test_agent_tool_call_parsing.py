#!/usr/bin/python
# -*- coding:utf-8 -*-

import json
from types import SimpleNamespace

from app.runtime.llm.agent_client import AgentLLM


class _FakeLLMClient:
    max_output_tokens = 128


class _ModelDumpObject:
    def __init__(self, value):
        self._value = value

    def model_dump(self):
        return self._value


def _build_llm():
    return AgentLLM(
        client=_FakeLLMClient(),
        model="test-model",
        context_window_tokens=2048,
        max_output_tokens=128,
    )


def _schema(*names):
    return [
        {"type": "function", "function": {"name": name}}
        for name in names
    ]


def _tool_call_payload(name="sql_agent"):
    return {
        "tool_calls": [{
            "id": "call_003",
            "type": "function",
            "function": {
                "name": name,
                "arguments": {"query": "查询已支付订单的总收入"},
            },
        }],
    }


def test_parses_tool_call_wrapped_in_double_outer_braces():
    llm = _build_llm()
    content = "{" + json.dumps(_tool_call_payload(), ensure_ascii=False) + "}"

    response = llm._build_response(
        SimpleNamespace(content=content, tool_calls=[]),
        tool_schema=_schema("sql_agent", "web_search"),
    )

    assert response["tool_calls"][0]["function"]["name"] == "sql_agent"
    assert response["tool_calls"][0]["function"]["arguments"] == {
        "query": "查询已支付订单的总收入"
    }


def test_parses_tool_call_inside_markdown_and_explanatory_text():
    llm = _build_llm()
    content = (
        "准备调用工具：\n```json\n"
        + json.dumps(_tool_call_payload("web_search"), ensure_ascii=False)
        + "\n```\n请稍候。"
    )

    response = llm._build_response(
        SimpleNamespace(content=content, tool_calls=[]),
        tool_schema=_schema("sql_agent", "web_search"),
    )

    assert response["tool_calls"][0]["function"]["name"] == "web_search"


def test_prefers_and_normalizes_provider_native_tool_calls():
    llm = _build_llm()
    native_call = _ModelDumpObject({
        "id": "native_1",
        "type": "function",
        "function": {
            "name": "sql_agent",
            "arguments": '{"query":"总收入"}',
        },
    })

    response = llm._build_response(
        SimpleNamespace(content="", tool_calls=[native_call]),
        tool_schema=_schema("sql_agent"),
    )

    assert response["tool_calls"] == [{
        "id": "native_1",
        "type": "function",
        "function": {
            "name": "sql_agent",
            "arguments": '{"query":"总收入"}',
        },
    }]


def test_does_not_promote_unknown_or_malformed_tool_calls():
    llm = _build_llm()
    unknown = json.dumps(_tool_call_payload("delete_everything"))
    malformed = '{"tool_calls": [{"function": {"arguments": {}}}]}'

    unknown_response = llm._build_response(
        SimpleNamespace(content=unknown, tool_calls=[]),
        tool_schema=_schema("sql_agent", "web_search"),
    )
    malformed_response = llm._build_response(
        SimpleNamespace(content=malformed, tool_calls=[]),
        tool_schema=_schema("sql_agent", "web_search"),
    )

    assert "tool_calls" not in unknown_response
    assert "tool_calls" not in malformed_response


def test_plain_answer_containing_tool_calls_words_is_not_a_tool_call():
    llm = _build_llm()
    content = "普通回答中提到了 tool_calls 字段，但没有提供工具调用 JSON。"

    response = llm._build_response(
        SimpleNamespace(content=content, tool_calls=[]),
        tool_schema=_schema("sql_agent"),
    )

    assert response == {"role": "assistant", "content": content}

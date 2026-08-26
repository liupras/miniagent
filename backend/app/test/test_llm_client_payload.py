#!/usr/bin/python
# -*- coding:utf-8 -*-

from app.runtime.llm.client import LLMClient


def test_completion_kwargs_strip_private_message_metadata():
    client = LLMClient(
        base_url="http://localhost:11434/v1",
        api_key="none",
        max_output_tokens=128,
    )
    messages = [
        {
            "role": "system",
            "content": "system prompt",
            "_tool_prompt": True,
        },
        {
            "role": "user",
            "content": "hello",
            "_trace_id": "private",
        },
    ]

    params = client._completion_kwargs(model="test-model", messages=messages)

    assert params["messages"] == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "hello"},
    ]
    assert params["max_tokens"] == 128
    assert messages[0]["_tool_prompt"] is True

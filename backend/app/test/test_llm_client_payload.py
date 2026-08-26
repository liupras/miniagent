#!/usr/bin/python
# -*- coding:utf-8 -*-

import asyncio
from types import SimpleNamespace

import app.runtime.llm.client as client_module
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


def test_explicit_output_limit_overrides_client_default():
    client = LLMClient(
        base_url="http://localhost:11434/v1",
        max_output_tokens=128,
    )
    messages = [{"role": "user", "content": "hello"}]

    with_max_tokens = client._completion_kwargs(
        model="test-model",
        messages=messages,
        max_tokens=32,
    )
    with_completion_tokens = client._completion_kwargs(
        model="test-model",
        messages=messages,
        max_completion_tokens=64,
    )

    assert with_max_tokens["max_tokens"] == 32
    assert "max_tokens" not in with_completion_tokens
    assert with_completion_tokens["max_completion_tokens"] == 64


def _response(content="ok"):
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=content, tool_calls=None),
        )],
        usage=SimpleNamespace(
            prompt_tokens=12,
            completion_tokens=3,
            total_tokens=15,
        ),
    )


def test_chat_and_achat_share_sanitized_payload_and_output_limit(monkeypatch):
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return _response("sync")

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        return _response("async")

    monkeypatch.setattr(client_module, "completion", fake_completion)
    monkeypatch.setattr(client_module, "acompletion", fake_acompletion)
    client = LLMClient(
        base_url="http://localhost:11434/v1",
        max_output_tokens=96,
    )
    messages = [{"role": "user", "content": "hello", "_private": True}]

    sync_response = client.chat("test-model", messages)
    async_response = asyncio.run(client.achat("test-model", messages))

    assert sync_response.content == "sync"
    assert async_response.content == "async"
    assert len(calls) == 2
    assert all(call["max_tokens"] == 96 for call in calls)
    assert all(call["messages"] == [{"role": "user", "content": "hello"}] for call in calls)


def test_stream_and_astream_share_sanitized_payload_and_output_limit(monkeypatch):
    calls = []
    chunk = SimpleNamespace(
        choices=[SimpleNamespace(
            delta=SimpleNamespace(content="chunk", reasoning_content=None),
        )]
    )

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return [chunk]

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)

        async def chunks():
            yield chunk

        return chunks()

    async def collect_async(client, messages):
        return [item async for item in client.astream("test-model", messages)]

    monkeypatch.setattr(client_module, "completion", fake_completion)
    monkeypatch.setattr(client_module, "acompletion", fake_acompletion)
    client = LLMClient(
        base_url="http://localhost:11434/v1",
        max_output_tokens=80,
    )
    messages = [{"role": "user", "content": "hello", "_private": True}]

    sync_chunks = list(client.stream("test-model", messages))
    async_chunks = asyncio.run(collect_async(client, messages))

    assert sync_chunks == ["chunk"]
    assert async_chunks == ["chunk"]
    assert len(calls) == 2
    assert all(call["max_tokens"] == 80 for call in calls)
    assert all(call["messages"] == [{"role": "user", "content": "hello"}] for call in calls)


def test_non_streaming_response_preserves_usage_and_logs_estimate(monkeypatch):
    debug_calls = []
    fake_logger = SimpleNamespace(
        debug=lambda *args, **kwargs: debug_calls.append((args, kwargs)),
        error=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(client_module, "logger", fake_logger)
    client = LLMClient(base_url="http://localhost:11434/v1")

    response = client._build_response(
        _response(),
        "test-model",
        prompt_messages=[{"role": "user", "content": "hello"}],
    )

    assert response.usage == {
        "prompt_tokens": 12,
        "completion_tokens": 3,
        "total_tokens": 15,
    }
    usage_log = next(args for args, _ in debug_calls if "Prompt token usage" in args[0])
    assert usage_log[1] == "test-model"
    assert isinstance(usage_log[2], int)
    assert usage_log[3] == 12


def test_usage_diagnostics_failure_does_not_break_model_response(monkeypatch):
    class BrokenTokenCounter:
        def __init__(self, **kwargs):
            pass

        def count_messages(self, *args, **kwargs):
            raise RuntimeError("diagnostics failed")

    fake_logger = SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(client_module, "TokenCounter", BrokenTokenCounter)
    monkeypatch.setattr(client_module, "logger", fake_logger)
    client = LLMClient(base_url="http://localhost:11434/v1")

    response = client._build_response(
        _response("still succeeds"),
        "test-model",
        prompt_messages=[{"role": "user", "content": "hello"}],
    )

    assert response.content == "still succeeds"
    assert response.usage["prompt_tokens"] == 12

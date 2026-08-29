#!/usr/bin/python
# -*- coding:utf-8 -*-

import asyncio
from types import SimpleNamespace

import pytest

import app.runtime.llm.client as client_module
from app.runtime.llm.client import LLMClient
from app.runtime.llm.models import LLMClientError
from app.core.i18n.error_translation import translate_domain_error


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


def test_achat_wraps_provider_errors_without_exposing_provider_detail(monkeypatch):
    async def fake_acompletion(**kwargs):
        raise ConnectionError("provider unavailable")

    monkeypatch.setattr(client_module, "acompletion", fake_acompletion)
    client = LLMClient(base_url="https://provider.example/v1")

    with pytest.raises(LLMClientError) as caught:
        asyncio.run(
            client.achat(
                "test-model",
                [{"role": "user", "content": "hello"}],
            )
        )

    assert isinstance(caught.value.cause, ConnectionError)
    assert "provider unavailable" not in translate_domain_error(caught.value)


def test_achat_wraps_response_parsing_errors_at_the_llm_boundary(monkeypatch):
    async def fake_acompletion(**kwargs):
        return SimpleNamespace(choices=[])

    monkeypatch.setattr(client_module, "acompletion", fake_acompletion)
    client = LLMClient(base_url="https://provider.example/v1")

    with pytest.raises(LLMClientError) as caught:
        asyncio.run(
            client.achat(
                "test-model",
                [{"role": "user", "content": "hello"}],
            )
        )

    assert isinstance(caught.value.cause, IndexError)


def test_chat_wraps_provider_errors(monkeypatch):
    def fake_completion(**kwargs):
        raise ConnectionError("provider unavailable")

    monkeypatch.setattr(client_module, "completion", fake_completion)
    client = LLMClient(base_url="https://provider.example/v1")

    with pytest.raises(LLMClientError) as caught:
        client.chat("test-model", [{"role": "user", "content": "hello"}])

    assert isinstance(caught.value.cause, ConnectionError)


def test_stream_wraps_errors_raised_during_iteration(monkeypatch):
    def fake_completion(**kwargs):
        def chunks():
            raise ConnectionError("stream interrupted")
            yield

        return chunks()

    monkeypatch.setattr(client_module, "completion", fake_completion)
    client = LLMClient(base_url="https://provider.example/v1")

    with pytest.raises(LLMClientError) as caught:
        list(client.stream("test-model", [{"role": "user", "content": "hello"}]))

    assert isinstance(caught.value.cause, ConnectionError)


def test_astream_wraps_errors_raised_during_iteration(monkeypatch):
    async def fake_acompletion(**kwargs):
        async def chunks():
            raise ConnectionError("stream interrupted")
            yield

        return chunks()

    async def collect(client):
        return [
            item
            async for item in client.astream(
                "test-model",
                [{"role": "user", "content": "hello"}],
            )
        ]

    monkeypatch.setattr(client_module, "acompletion", fake_acompletion)
    client = LLMClient(base_url="https://provider.example/v1")

    with pytest.raises(LLMClientError) as caught:
        asyncio.run(collect(client))

    assert isinstance(caught.value.cause, ConnectionError)


def test_embed_and_aembed_use_the_same_boundary_error(monkeypatch):
    def fake_embedding(**kwargs):
        raise ConnectionError("embedding unavailable")

    async def fake_aembedding(**kwargs):
        raise ConnectionError("embedding unavailable")

    monkeypatch.setattr(client_module, "embedding", fake_embedding)
    monkeypatch.setattr(client_module, "aembedding", fake_aembedding)
    client = LLMClient(base_url="https://provider.example/v1")

    with pytest.raises(LLMClientError) as sync_caught:
        client.embed("embedding-model", ["hello"])
    with pytest.raises(LLMClientError) as async_caught:
        asyncio.run(client.aembed("embedding-model", ["hello"]))

    assert isinstance(sync_caught.value.cause, ConnectionError)
    assert isinstance(async_caught.value.cause, ConnectionError)


def test_async_llm_call_does_not_wrap_cancellation(monkeypatch):
    async def fake_acompletion(**kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(client_module, "acompletion", fake_acompletion)
    client = LLMClient(base_url="https://provider.example/v1")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            client.achat(
                "test-model",
                [{"role": "user", "content": "hello"}],
            )
        )


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

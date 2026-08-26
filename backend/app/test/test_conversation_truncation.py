#!/usr/bin/python
# -*- coding:utf-8 -*-

from copy import deepcopy

import pytest

from app.runtime.llm.func import TRUNCATION_MARKER, truncate_messages
from app.utils.tokens import TokenCounter


def _counter():
    return TokenCounter(model="test-model", enable_exact_near_limit=False)


def test_messages_are_returned_unchanged_when_they_fit():
    counter = _counter()
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "current question"},
    ]
    original = deepcopy(messages)

    result = truncate_messages(messages, 1000, token_counter=counter)

    assert result == original
    assert messages == original
    assert result is not messages


def test_oldest_complete_turns_are_removed_first():
    counter = _counter()
    system = {"role": "system", "content": "system"}
    old_turn = [
        {"role": "user", "content": "old question " + "x" * 500},
        {"role": "assistant", "content": "old answer " + "y" * 500},
    ]
    recent_turn = [
        {"role": "user", "content": "recent question"},
        {"role": "assistant", "content": "recent answer"},
    ]
    current = {"role": "user", "content": "current question"}
    expected = [system] + recent_turn + [current]
    budget = counter.count_messages(expected)

    result = truncate_messages(
        [system] + old_turn + recent_turn + [current],
        budget,
        token_counter=counter,
    )

    assert result == expected
    assert counter.count_messages(result) <= budget


def test_user_assistant_history_is_kept_as_an_atomic_turn():
    counter = _counter()
    system = {"role": "system", "content": "system"}
    history_turn = [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer " + "x" * 500},
    ]
    current = {"role": "user", "content": "current"}
    budget = counter.count_messages([system, current]) + 5

    result = truncate_messages(
        [system] + history_turn + [current],
        budget,
        token_counter=counter,
    )

    assert result == [system, current]


def test_oversized_current_message_is_token_budget_truncated_without_mutation():
    counter = _counter()
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "current-" + "x" * 2000},
    ]
    original = deepcopy(messages)
    minimum = counter.count_messages([
        messages[0],
        {"role": "user", "content": TRUNCATION_MARKER},
    ])
    budget = minimum + 40

    result = truncate_messages(messages, budget, token_counter=counter)

    assert result[-1]["content"].endswith(TRUNCATION_MARKER)
    assert len(result[-1]["content"]) < len(messages[-1]["content"])
    assert counter.count_messages(result) <= budget
    assert messages == original


def test_system_prompt_is_never_silently_truncated():
    counter = _counter()
    messages = [
        {"role": "system", "content": "system-" * 1000},
        {"role": "user", "content": "current"},
    ]

    with pytest.raises(ValueError, match="System prompts"):
        truncate_messages(messages, 100, token_counter=counter)


def test_model_tokenizer_can_tighten_lightweight_truncation_near_limit():
    exact_calls = []

    def character_tokenizer(**kwargs):
        exact_calls.append(kwargs)
        messages = kwargs["messages"]
        return sum(
            len(str(message.get("content", ""))) + 5
            for message in messages
        )

    counter = TokenCounter(
        model="test-model",
        exact_threshold_ratio=0.01,
        exact_counter=character_tokenizer,
    )
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "x" * 1000},
    ]
    budget = 120

    result = truncate_messages(messages, budget, token_counter=counter)

    assert exact_calls
    assert result[-1]["content"].endswith(TRUNCATION_MARKER)
    assert counter.count_messages(result, budget=budget) <= budget


def test_rejects_non_chronological_system_or_missing_current_user():
    counter = _counter()

    with pytest.raises(ValueError, match="must precede"):
        truncate_messages([
            {"role": "user", "content": "history"},
            {"role": "system", "content": "late system"},
            {"role": "user", "content": "current"},
        ], 10, token_counter=counter)

    with pytest.raises(ValueError, match="final conversation message"):
        truncate_messages([
            {"role": "system", "content": "system"},
            {"role": "assistant", "content": "not a current user message"},
        ], 10, token_counter=counter)

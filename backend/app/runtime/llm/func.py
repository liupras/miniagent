#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-01-19
# @description: Utility functions

from copy import deepcopy
from typing import Any, Generator, List, Dict, Optional

from app.utils.tokens import TokenCounter, sanitize_chat_messages
from app.runtime.types import MessageRole

TRUNCATION_MARKER = "\n[Content truncated to fit the model context window]"

def truncate_messages(
    messages: List[Dict[str, Any]],
    max_token: int,
    token_counter: Optional[TokenCounter] = None,
) -> List[Dict[str, Any]]:
    """Fit a chronological ordinary conversation into ``max_token``.

    Leading system messages and the current (last) user message are fixed.
    Historical user/assistant turns are retained atomically from newest to
    oldest. The input collection and its dictionaries are never mutated.
    """
    if max_token <= 0:
        raise ValueError("max_token must be greater than zero")

    counter = token_counter or TokenCounter(enable_exact_near_limit=False)
    provider_messages = sanitize_chat_messages(deepcopy(messages))
    if not provider_messages:
        return []

    system_messages, body = _split_leading_system_messages(provider_messages)
    if any(message.get("role") == MessageRole.SYSTEM for message in body):
        raise ValueError("System messages must precede conversation messages")

    if not body:
        if _messages_fit(provider_messages, max_token, counter):
            return provider_messages
        raise ValueError("System prompts exceed the available input token budget")
    if body[-1].get("role") != MessageRole.USER:
        raise ValueError("The current user message must be the final conversation message")

    if _messages_fit(provider_messages, max_token, counter):
        return provider_messages

    system_tokens = counter.count_messages(system_messages, budget=max_token)
    if system_tokens >= max_token:
        raise ValueError("System prompts exceed the available input token budget")

    current_message = body[-1]
    current_context = system_messages + [current_message]
    if not _messages_fit(current_context, max_token, counter):
        current_message = _truncate_message_to_fit(
            prefix=system_messages,
            message=current_message,
            max_token=max_token,
            counter=counter,
        )

    history_turns = _split_history_turns(body[:-1])
    selected_turns: List[List[Dict[str, Any]]] = []
    for turn in reversed(history_turns):
        candidate_turns = [turn] + selected_turns
        candidate = (
            system_messages
            + [message for item in candidate_turns for message in item]
            + [current_message]
        )
        if not _messages_fit(candidate, max_token, counter):
            break
        selected_turns = candidate_turns

    result = (
        system_messages
        + [message for turn in selected_turns for message in turn]
        + [current_message]
    )

    # A model tokenizer may count more than the lightweight estimator. Remove
    # oldest complete turns first, then shrink only the current user content.
    while selected_turns and not _messages_fit(result, max_token, counter):
        selected_turns.pop(0)
        result = (
            system_messages
            + [message for turn in selected_turns for message in turn]
            + [current_message]
        )

    if not _messages_fit(result, max_token, counter):
        current_message = _truncate_message_to_fit(
            prefix=system_messages,
            message=current_message,
            max_token=max_token,
            counter=counter,
        )
        result = system_messages + [current_message]

    if not _messages_fit(result, max_token, counter):
        raise ValueError("Unable to fit the current conversation into the input budget")
    return result


def _messages_fit(
    messages: List[Dict[str, Any]],
    max_token: int,
    counter: TokenCounter,
    allow_exact: bool = True,
) -> bool:
    if allow_exact:
        # TokenCounter invokes the local tokenizer only near the limit.
        return counter.count_messages(messages, budget=max_token) <= max_token
    return counter.count_messages(messages) <= max_token


def _split_leading_system_messages(
    messages: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    boundary = 0
    for message in messages:
        if message.get("role") != MessageRole.SYSTEM:
            break
        boundary += 1
    return messages[:boundary], messages[boundary:]


def _split_history_turns(
    messages: List[Dict[str, Any]],
) -> List[List[Dict[str, Any]]]:
    """Group history by user turns and discard orphan/unsupported messages."""
    turns: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == MessageRole.USER:
            if current:
                turns.append(current)
            current = [message]
        elif role == MessageRole.ASSISTANT and current:
            current.append(message)
    if current:
        turns.append(current)
    return turns


def _truncate_message_to_fit(
    prefix: List[Dict[str, Any]],
    message: Dict[str, Any],
    max_token: int,
    counter: TokenCounter,
) -> Dict[str, Any]:
    content = str(message.get("content", ""))
    empty_message = {**message, "content": ""}
    if not _messages_fit(prefix + [empty_message], max_token, counter):
        raise ValueError("System prompts leave no room for the current user message")

    marker_message = {**message, "content": TRUNCATION_MARKER}
    if not _messages_fit(prefix + [marker_message], max_token, counter):
        return empty_message

    low, high = 0, len(content)
    best = marker_message
    while low <= high:
        middle = (low + high) // 2
        candidate = {
            **message,
            "content": content[:middle] + TRUNCATION_MARKER,
        }
        if _messages_fit(
            prefix + [candidate],
            max_token,
            counter,
            allow_exact=False,
        ):
            best = candidate
            low = middle + 1
        else:
            high = middle - 1

    if _messages_fit(prefix + [best], max_token, counter):
        return best

    # Rare fallback: the model tokenizer counted more than the lightweight
    # estimate. Repeat the search with exact-near-limit checks enabled.
    low, high = 0, max(0, len(best.get("content", "")) - len(TRUNCATION_MARKER))
    exact_best = marker_message
    while low <= high:
        middle = (low + high) // 2
        candidate = {
            **message,
            "content": content[:middle] + TRUNCATION_MARKER,
        }
        if _messages_fit(prefix + [candidate], max_token, counter):
            exact_best = candidate
            low = middle + 1
        else:
            high = middle - 1
    return exact_best

def generate_stream_response(generator: Generator[str, None, None]):
    """Convert the generator to SSE streaming response format"""
    for chunk in generator:
        if chunk:
            # SSE format: data: content\n\n
            yield f"data: {chunk}\n\n"
    # Streaming end marker
    yield "data: [DONE]\n\n"

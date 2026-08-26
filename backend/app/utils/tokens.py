#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-25
# @description: utility functions for the application

import json
import math
import unicodedata
from typing import Any, Callable, Dict, List, Optional

from app.core.logger_config import get_logger

logger = get_logger(__name__)


ExactTokenCounter = Callable[..., int]


def sanitize_chat_messages(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return the provider payload without MiniAgent's private metadata."""
    return [
        {
            key: value
            for key, value in message.items()
            if not (isinstance(key, str) and key.startswith("_"))
        }
        for message in messages
    ]


class TokenCounter:
    """Low-cost token counter with an optional near-limit exact pass.

    The lightweight estimator is always evaluated first. LiteLLM's local
    tokenizer is imported and called only when the estimate reaches
    ``exact_threshold_ratio`` of the supplied budget. No LLM request is made.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        exact_threshold_ratio: float = 0.85,
        enable_exact_near_limit: bool = True,
        exact_counter: Optional[ExactTokenCounter] = None,
    ) -> None:
        if not 0 < exact_threshold_ratio <= 1:
            raise ValueError("exact_threshold_ratio must be in the range (0, 1]")

        self.model = model or ""
        self.exact_threshold_ratio = exact_threshold_ratio
        self.enable_exact_near_limit = enable_exact_near_limit
        self._exact_counter = exact_counter

    def count_text(self, text: Any, budget: Optional[int] = None) -> int:
        """Count text cheaply, using a local tokenizer only near ``budget``."""
        normalized = "" if text is None else str(text)
        lightweight = self._count_text_lightweight(normalized)
        if not self._should_try_exact(lightweight, budget):
            return lightweight

        return self._try_exact(
            lightweight,
            text=normalized,
        )

    def count_messages(
        self,
        messages: List[Dict[str, Any]],
        budget: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """Count the complete chat payload, including tool metadata."""
        self._validate_budget(budget)
        if not messages and not tools:
            return 0

        provider_messages = sanitize_chat_messages(messages)
        payload: Dict[str, Any] = {"messages": provider_messages}
        if tools:
            payload["tools"] = tools
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        lightweight = self._count_text_lightweight(serialized)
        if not self._should_try_exact(lightweight, budget):
            return lightweight

        return self._try_exact(
            lightweight,
            messages=provider_messages,
            tools=tools,
        )

    def _should_try_exact(
        self,
        lightweight_count: int,
        budget: Optional[int],
    ) -> bool:
        self._validate_budget(budget)
        if (
            budget is None
            or not self.enable_exact_near_limit
            or not self.model
        ):
            return False
        return lightweight_count >= math.ceil(
            budget * self.exact_threshold_ratio
        )

    def _try_exact(self, fallback: int, **kwargs: Any) -> int:
        try:
            counter = self._exact_counter or self._litellm_token_counter
            exact = counter(model=self.model, **kwargs)
            if isinstance(exact, bool) or not isinstance(exact, int) or exact <= 0:
                raise ValueError(f"invalid tokenizer result: {exact!r}")
            return exact
        except Exception as exc:
            logger.debug(
                "[TokenCounter] Local tokenizer unavailable for model '{}'; "
                "using lightweight estimate: {}",
                self.model,
                exc,
            )
            return fallback

    @staticmethod
    def _validate_budget(budget: Optional[int]) -> None:
        if budget is not None and budget <= 0:
            raise ValueError("budget must be greater than zero")

    @staticmethod
    def _litellm_token_counter(**kwargs: Any) -> int:
        # Lazy import avoids loading LiteLLM/tokenizer resources for ordinary
        # requests that are comfortably below the context limit.
        from litellm import token_counter

        return token_counter(**kwargs)

    @staticmethod
    def _count_text_lightweight(text: str) -> int:
        if not text:
            return 0

        dense_script_chars = 0
        ascii_word_chars = 0
        whitespace_chars = 0
        punctuation_chars = 0
        other_text_chars = 0
        symbol_chars = 0

        for char in text:
            codepoint = ord(char)
            if TokenCounter._is_dense_script(codepoint):
                dense_script_chars += 1
            elif char.isspace():
                whitespace_chars += 1
            elif char.isascii() and char.isalnum():
                ascii_word_chars += 1
            else:
                category = unicodedata.category(char)
                if category.startswith("S"):
                    symbol_chars += 1
                elif category.startswith(("L", "N")):
                    other_text_chars += 1
                else:
                    punctuation_chars += 1

        raw_estimate = (
            dense_script_chars
            + ascii_word_chars / 3.5
            + whitespace_chars / 6
            + punctuation_chars / 2
            + other_text_chars / 2
            + symbol_chars * 2
        )
        # Keep the estimator conservative while guaranteeing that every
        # non-empty input consumes at least one token.
        return max(1, math.ceil(raw_estimate * 1.1))

    @staticmethod
    def _is_dense_script(codepoint: int) -> bool:
        return (
            0x3400 <= codepoint <= 0x4DBF       # CJK Extension A
            or 0x4E00 <= codepoint <= 0x9FFF    # CJK Unified Ideographs
            or 0xF900 <= codepoint <= 0xFAFF    # CJK Compatibility
            or 0x20000 <= codepoint <= 0x2FA1F  # CJK Extensions B-F
            or 0x3040 <= codepoint <= 0x30FF    # Hiragana / Katakana
            or 0xAC00 <= codepoint <= 0xD7AF    # Hangul syllables
        )


_DEFAULT_TOKEN_COUNTER = TokenCounter(enable_exact_near_limit=False)


def estimate_tokens(text: str, model_family="qwen") -> int:
    """
    Backward-compatible lightweight token estimate.

    ``model_family`` is retained for existing callers. Model-aware exact
    counting is available through ``TokenCounter`` when a budget is supplied.
    """
    return _DEFAULT_TOKEN_COUNTER.count_text(text)

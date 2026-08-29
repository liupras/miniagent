#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-27
# @description: Token-safe preparation of text sent to embedding models.

import math
from typing import Optional

from app.core.logger_config import get_logger
from app.schemas.exceptions import InfrastructureError
from app.utils.tokens import TokenCounter

logger = get_logger(__name__)


class EmbeddingInputTooLongError(InfrastructureError):
    """Raised when even the smallest input cannot fit the configured budget."""

    error_key = "embedding.input_too_long"


class EmbeddingInputGuard:
    """Apply a safety margin to an embedding model's per-input token limit."""

    def __init__(
        self,
        max_input_tokens: int,
        model: Optional[str] = None,
        safety_ratio: float = 0.95,
        token_counter: Optional[TokenCounter] = None,
    ) -> None:
        if max_input_tokens <= 0:
            raise ValueError("max_input_tokens must be greater than zero")
        if not 0 < safety_ratio <= 1:
            raise ValueError("safety_ratio must be in the range (0, 1]")

        self.max_input_tokens = max_input_tokens
        self.safe_input_tokens = max(
            1,
            math.floor(max_input_tokens * safety_ratio),
        )
        self.token_counter = token_counter or TokenCounter(model=model)

    def count(self, text: str) -> int:
        return self.token_counter.count_text(
            text,
            budget=self.safe_input_tokens,
        )

    def fits(self, text: str) -> bool:
        return self.count(text) <= self.safe_input_tokens

    def split_text(self, text: str) -> list[str]:
        """Split an oversized text into non-empty token-safe pieces."""
        if not text or self.fits(text):
            return [text]

        pieces: list[str] = []
        remaining = text
        while remaining:
            if self.fits(remaining):
                pieces.append(remaining)
                break

            split_at = self._largest_fitting_prefix(remaining)
            pieces.append(remaining[:split_at])
            remaining = remaining[split_at:]

        return pieces

    def truncate_text(self, text: str) -> str:
        """Return the first token-safe portion of an oversized query text."""
        if not text or self.fits(text):
            return text

        pieces = self.split_text(text)
        truncated = pieces[0] if pieces else ""
        logger.warning(
            "[Embedding] Input truncated from {} to approximately {} tokens "
            "(safe limit={}).",
            self.count(text),
            self.count(truncated),
            self.safe_input_tokens,
        )
        return truncated

    def _largest_fitting_prefix(self, text: str) -> int:
        low = 1
        high = len(text) - 1
        best = 0

        while low <= high:
            midpoint = (low + high) // 2
            if self.fits(text[:midpoint]):
                best = midpoint
                low = midpoint + 1
            else:
                high = midpoint - 1

        if best == 0:
            raise EmbeddingInputTooLongError(
                "A single character exceeds the embedding input token budget"
            )
        return best

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-24
# @description: Shared AdaptiveThresholdStage logic, used by both
#               retrieval.py (RetrievalPipeline) and web_search.py (WebSearchPipeline).
#
# Algorithm
# ─────────
#   threshold = mean(scores) − std_factor × stdev(scores)
#   Keep all items whose final_score >= threshold.
#   Always keep at least min_keep items (fallback: top-N by list order).
#   Skip filtering if fewer than 3 items are present (statistics unreliable).

from __future__ import annotations

import statistics
from typing import List, TypeVar

from loguru import logger

# T represents any object that has a `final_score: float` attribute.
T = TypeVar("T")


class AdaptiveThresholdMixin:
    """
    Pure-computation mixin for adaptive score-based filtering.

    Subclasses must set:
        self._std_factor : float   — multiplier for standard deviation
        self._min_keep   : int     — minimum number of items to retain

    Subclasses call:
        filtered = self._apply_threshold(items)

    where `items` is any list of objects that expose a `final_score` float attribute.
    """

    _std_factor: float
    _min_keep: int

    def _apply_threshold(self, items: List[T]) -> List[T]:
        """
        Filter *items* by adaptive score threshold.

        Returns the filtered list (or the original list unchanged if there are
        fewer than 3 items).
        """
        if len(items) < 3:
            return items

        scores = [item.final_score for item in items]  # type: ignore[attr-defined]
        mean = statistics.mean(scores)
        std = statistics.stdev(scores)
        threshold = mean - self._std_factor * std

        filtered = [item for item in items if item.final_score >= threshold]  # type: ignore[attr-defined]
        if len(filtered) < self._min_keep:
            filtered = items[: self._min_keep]

        logger.debug(
            f"[AdaptiveThreshold] mean={mean:.3f}  std={std:.3f}  "
            f"threshold={threshold:.3f}  kept={len(filtered)}"
        )
        return filtered

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-15
# @description: Per-task SSE event queue.

import asyncio
from datetime import datetime
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Progress tracker  (per-task SSE event queue)
# ─────────────────────────────────────────────────────────────────────────────

class ProgressTracker:
    """
    Each active task gets an asyncio.Queue drained by the SSE endpoint.
    Event schema: {stage, message, progress(0-100), done, error, ts}
    """
    _queues: dict[str, asyncio.Queue] = {}

    @classmethod
    def create(cls, task_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        cls._queues[task_id] = q
        return q

    @classmethod
    def get(cls, task_id: str) -> Optional[asyncio.Queue]:
        return cls._queues.get(task_id)

    @classmethod
    def remove(cls, task_id: str) -> None:
        cls._queues.pop(task_id, None)

    @classmethod
    async def emit(
        cls,
        task_id:  str,
        stage:    str,
        message:  str,
        progress: float = 0.0,
        done:     bool  = False,
        error:    bool  = False,
    ) -> None:
        q = cls._queues.get(task_id)
        if q:
            await q.put({
                "stage":    stage,
                "message":  message,
                "progress": round(progress, 1),
                "done":     done,
                "error":    error,
                "ts":       datetime.now().isoformat(),
            })


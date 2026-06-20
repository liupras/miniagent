#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-15
# @description: Per-task SSE event queue.

import asyncio
from datetime import datetime
from enum import Enum
from typing import Optional

class DocumentStatus(Enum):
    """Document processing status enumeration"""
    PROCESSING = "processing"
    COMPLETED  = "completed"
    FAILED     = "failed"
    
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
    def get_or_create(cls, task_id: str) -> asyncio.Queue:
        if task_id not in cls._queues:
            cls._queues[task_id] = asyncio.Queue(maxsize=200)
        return cls._queues[task_id]

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

    @classmethod
    def emit_sync(cls, task_id: str, stage: str, message: str, progress: float, done: bool = False, error: bool = False):
        """Synchronized thread/method-safe event emitters"""
        q = cls._queues.get(task_id)
        if q:
            event = {
                "stage": stage,
                "message": message,
                "progress": round(progress, 1),
                "done": done,
                "error": error,
                "ts": datetime.now().isoformat(),
            }
            try:
                # Get the current thread's event loop and safely write it to the asynchronous queue.
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(q.put_nowait, event)
            except RuntimeError:
                pass

def emitter(task_id: str):
    """Return an async callable bound to a specific task_id."""
    async def _emit(stage, message, progress=0.0, done=False, error=False):
        await ProgressTracker.emit(task_id, stage, message, progress, done, error)
    return _emit
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-21
# @description: SSE — real-time progress stream.


import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.runtime.task.progress_tracker import ProgressTracker
from app.schemas.common import ApiResponse
from app.core.i18n.i18n import t

router = APIRouter()

@router.get(
    "/{task_id}/progress",
    summary="SSE — real-time task progress"
)
async def task_progress(
    task_id: str,
):
    """
    Server-Sent Events stream.  Connect and receive JSON events until
    `done=true` or `error=true`.

    **Event shape**
    ```json
    {
      "stage":    "embed",
      "message":  "🧠 Embedding 64/128 chunks …",
      "progress": 72.5,
      "done":     false,
      "error":    false,
      "ts":       "2026-02-27T10:00:00.000000"
    }
    ```
    """
    queue = ProgressTracker.get(task_id)
    if queue is None:
        return ApiResponse(code=404,message=t("task.not_found_or_finished"))

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("done") or event.get("error"):
                    break
        finally:
            ProgressTracker.remove(task_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-17
# @description: routes for AgentFactory usage.

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel,Field

router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# Request / Response models
# ─────────────────────────────────────────────────────────────────────────────

class ChatTurn(BaseModel):
    role: str                   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    query: str = ""
    history: Optional[List[ChatTurn]] = Field(None, example=[])

    # ── Multi-turn persistent memory ──────────────────────────────────────
    # When both fields are provided the runner will automatically load prior
    # turns from the DB and save the new user/assistant messages.
    # Omit both fields for the original stateless (single-turn) behaviour.
    user_id: Optional[str] = "demo"
    session_id: Optional[str] = "ca97ac69-bce8-4752-8e89-1143eacdb087"


class ChatResponse(BaseModel):
    answer: str
    agent_id: int


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _get_factory(request: Request):
    """Extract AgentFactory from app.state.container (set at startup)."""
    return request.app.state.container.agent_factory


def _history_to_dicts(history: Optional[List[ChatTurn]]):
    if not history:
        return None   # None → runner will fall back to DB history (if available)
    return [{"role": t.role, "content": t.content} for t in history]


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{agent_id}/chat", response_model=ChatResponse)
async def chat(
    agent_id: int,
    body: ChatRequest,
    factory=Depends(_get_factory),
):
    """
    One-shot chat: returns the full answer once the agent finishes.

    Persistent memory is enabled automatically when ``user_id`` and
    ``session_id`` are present in the request body.
    """
    try:
        runner = await factory.get_runner(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    answer = await runner.invoke(
        query=body.query,
        history=_history_to_dicts(body.history),
        user_id=body.user_id,
        session_id=body.session_id,
    )
    return ChatResponse(answer=answer, agent_id=agent_id)


@router.post("/{agent_id}/chat/stream")
async def chat_stream(
    agent_id: int,
    body: ChatRequest,
    factory=Depends(_get_factory),
):
    """
    Streaming chat — returns an SSE stream.

    Each SSE event carries one text fragment; the stream ends with
    ``data: [DONE]\\n\\n`` following the same convention as client.py.

    Persistent memory is enabled automatically when ``user_id`` and
    ``session_id`` are present in the request body.
    """
    try:
        runner = await factory.get_runner(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    async def _sse_generator():
        async for chunk in runner.stream(
            query=body.query,
            history=_history_to_dicts(body.history),
            user_id=body.user_id,
            session_id=body.session_id,
        ):
            if chunk:
                yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable Nginx buffering
        },
    )


@router.delete("/{agent_id}/cache", status_code=204)
async def invalidate_agent_cache(
    agent_id: int,
    factory=Depends(_get_factory),
):
    """
    Evict the cached AgentRunner for *agent_id*.

    Call this after updating the agent's configuration, tools, or LLM settings
    so the next request picks up the latest DB state.
    """
    factory.invalidate(agent_id)
    return None


@router.delete("/cache", status_code=204)
async def invalidate_all_agent_cache(factory=Depends(_get_factory)):
    """Evict ALL cached AgentRunners (e.g. after a system language change)."""
    factory.invalidate()
    return None

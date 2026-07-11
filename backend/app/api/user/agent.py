#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Gemini Collaborator
# @date    : 2026-07-07
# @description: FastAPI router — Agent Testing & Evaluation endpoints

from __future__ import annotations
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sse_starlette.sse import EventSourceResponse
from loguru import logger

from app.schemas.user.agent import AgentRequest
from app.schemas.common import ApiResponse
from app.runtime.agent.agent_factory import AgentFactory
from app.core.i18n.i18n import t

router = APIRouter()

# ═══════════════════════════════════════════════════════════════════════════
# Dependency helpers
# ═══════════════════════════════════════════════════════════════════════════

def _get_agent_factory(request: Request) -> AgentFactory:
    """
    Retrieve the AgentFactory instance from the global application state container.
    """
    return request.app.state.container.agent_factory

# ═══════════════════════════════════════════════════════════════════════════
# Helper Internal Function
# ═══════════════════════════════════════════════════════════════════════════

async def _resolve_runner(body: AgentRequest, factory: AgentFactory):
    """
    Resolve the corresponding AgentRunner instance based on the id or name in the request body.
    """
  
    if body.agent_id is not None:
        return await factory.get_runner(body.agent_id)
    elif body.agent_name:
        return await factory.get_runner_by_name(body.agent_name)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("agent.input_invalid")
        )
    
# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/invoke", response_model=ApiResponse, summary="Single synchronous call to Agent interface")
async def agent_invoke(
    body: AgentRequest,
    factory: AgentFactory = Depends(_get_agent_factory)
) -> ApiResponse:
    """
    Run the Agent until it finishes responding, then return the final text result all at once.
    """
    runner = await _resolve_runner(body, factory)    

    logger.info(f"[AgentTest] Invoking agent '{runner.agent_name}' with query: '{body.query}'")
    answer = await runner.invoke(
        query=body.query,
        history=body.history,
        user_id=body.user_id,
        session_id=body.session_id
    )
    return ApiResponse(data={"answer": answer})


@router.post("/stream", summary="Streaming Token Output Call Agent Interface")
async def agent_stream(
    request: Request,
    body: AgentRequest,
    factory: AgentFactory = Depends(_get_agent_factory)
):
    """
    Stream Agent’s thought or response tokens using the Server-Sent Events (SSE) protocol.
    """
    runner = await _resolve_runner(body, factory)
    
    logger.info(f"[AgentTest] Streaming agent '{runner.agent_name}' with query: '{body.query}'")

    text_generator = runner.stream(
        query=body.query, 
        session_id=body.session_id, 
        user_id=body.user_id,
        history=body.history
    )

    async def sse_event_publisher():
        async for chunk_str in text_generator:
            if await request.is_disconnected():
                break
                
            data_dict = json.loads(chunk_str)
            yield {
                "event": data_dict["event"],
                "data": chunk_str
            }

    return EventSourceResponse(sse_event_publisher())
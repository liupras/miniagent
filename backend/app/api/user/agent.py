#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Gemini Collaborator
# @date    : 2026-07-07
# @description: FastAPI router — Agent Testing & Evaluation endpoints

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from loguru import logger

from app.schemas.user.agent import AgentRequest
from app.schemas.common import ApiResponse
from app.runtime.agent_factory import AgentFactory
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
    
    try:
        logger.info(f"[AgentTest] Invoking agent '{runner.agent_name}' with query: '{body.query}'")
        answer = await runner.invoke(
            query=body.query,
            history=body.history,
            user_id=body.user_id,
            session_id=body.session_id
        )
        return ApiResponse(data={"answer": answer})
    except Exception as exc:
        logger.error(f"Agent invoke encountered an error: {exc}")
        return ApiResponse(code=500, message=f"Internal Agent Error: {str(exc)}")


@router.post("/stream", summary="Streaming Token Output Call Agent Interface")
async def agent_stream(
    body: AgentRequest,
    factory: AgentFactory = Depends(_get_agent_factory)
):
    """
    Stream Agent’s thought or response tokens using the Server-Sent Events (SSE) protocol.
    """
    runner = await _resolve_runner(body, factory)
    
    logger.info(f"[AgentTest] Streaming agent '{runner.agent_name}' with query: '{body.query}'")

    async def sse_event_generator():
        try:
            async for token in runner.stream(
                query=body.query,
                history=body.history,
                user_id=body.user_id,
                session_id=body.session_id
            ):
                # Packaged as a standard SSE text block format returned
                yield f"data: {token}\n\n"
        except Exception as exc:
            logger.error(f"Error during agent streaming: {exc}")
            yield f"data: [ERROR: {str(exc)}]\n\n"

    return StreamingResponse(sse_event_generator(), media_type="text/event-stream")
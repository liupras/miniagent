#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Gemini Collaborator
# @date    : 2026-07-07
# @description: Authenticated Workplace agent and conversation endpoints.

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings
from app.core.i18n.i18n import t
from app.core.logger_config import get_logger
from app.core.security.auth_permission import AuthPermission
from app.schemas.common import ApiResponse
from app.schemas.user.agent import AgentRequest, RenameSessionRequest
from app.services.workplace_agent import WorkplaceAgentService


logger = get_logger(__name__)
router = APIRouter()
current_user = AuthPermission.CurrentUser()


def _get_service(request: Request) -> WorkplaceAgentService:
    return request.app.state.container.workplace_agent_service


def _session_payload(item) -> dict:
    return {
        "session_id": item.id,
        "title": item.title,
        "agent_id": item.agent_id,
        "agent_name": item.agent.name if item.agent else None,
        "message_count": item.message_count or 0,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.get("/available", response_model=ApiResponse, summary="List assigned agents")
async def list_available_agents(
    service: WorkplaceAgentService = Depends(_get_service),
    user_id: int = Depends(current_user),
) -> ApiResponse:
    agents = await service.list_available_agents(user_id)
    return ApiResponse(
        data={
            "version": settings.app_version,
            "items": [
                {
                    "id": agent.id,
                    "name": agent.name,
                    "description": agent.description,
                }
                for agent in agents
            ],
        }
    )


@router.get("/sessions", response_model=ApiResponse, summary="List my sessions")
async def list_my_sessions(
    query: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    service: WorkplaceAgentService = Depends(_get_service),
    user_id: int = Depends(current_user),
) -> ApiResponse:
    total, items = await service.list_user_sessions(
        user_id=user_id,
        page=page,
        page_size=page_size,
        query=query,
    )
    return ApiResponse(
        data={
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [_session_payload(item) for item in items],
        }
    )


@router.get(
    "/sessions/{session_id}/messages",
    response_model=ApiResponse,
    summary="List messages in one of my sessions",
)
async def list_my_messages(
    session_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=500),
    service: WorkplaceAgentService = Depends(_get_service),
    user_id: int = Depends(current_user),
) -> ApiResponse:
    total, items = await service.list_user_messages(
        session_id=session_id,
        user_id=user_id,
        page=page,
        page_size=page_size,
    )
    return ApiResponse(
        data={
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": item.id,
                    "session_id": item.session_id,
                    "role": item.role,
                    "content": item.content,
                    "created_at": (
                        item.created_at.isoformat() if item.created_at else None
                    ),
                }
                for item in items
            ],
        }
    )


@router.patch(
    "/sessions/{session_id}",
    response_model=ApiResponse,
    summary="Rename one of my sessions",
)
async def rename_my_session(
    session_id: int,
    body: RenameSessionRequest,
    service: WorkplaceAgentService = Depends(_get_service),
    user_id: int = Depends(current_user),
) -> ApiResponse:
    title = await service.rename_user_session(session_id, user_id, body.title)
    return ApiResponse(data={"session_id": session_id, "title": title})


@router.delete(
    "/sessions/{session_id}",
    response_model=ApiResponse,
    summary="Delete one of my sessions",
)
async def delete_my_session(
    session_id: int,
    service: WorkplaceAgentService = Depends(_get_service),
    user_id: int = Depends(current_user),
) -> ApiResponse:
    await service.delete_user_session(session_id, user_id)
    return ApiResponse()


@router.post("/invoke", response_model=ApiResponse, summary="Invoke an assigned agent")
async def agent_invoke(
    body: AgentRequest,
    service: WorkplaceAgentService = Depends(_get_service),
    user_id: int = Depends(current_user),
) -> ApiResponse:
    answer, session_id = await service.invoke(
        user_id=user_id,
        agent_id=body.agent_id,
        agent_name=body.agent_name,
        session_id=body.session_id,
        query=body.query,
        history=body.history or None,
    )
    return ApiResponse(data={"answer": answer, "session_id": session_id})


@router.post("/stream", summary="Stream an assigned agent response over SSE")
async def agent_stream(
    request: Request,
    body: AgentRequest,
    service: WorkplaceAgentService = Depends(_get_service),
    user_id: int = Depends(current_user),
):
    runner, chat_session = await service.prepare_call(
        user_id=user_id,
        agent_id=body.agent_id,
        agent_name=body.agent_name,
        session_id=body.session_id,
    )

    logger.info(
        "[Workplace] Streaming agent '{}' for user_id={} session_id={}",
        runner.agent_name,
        user_id,
        chat_session.id,
    )

    async def sse_event_publisher():
        yield {
            "event": "session",
            "data": json.dumps(
                {"event": "session", "session_id": chat_session.id},
                ensure_ascii=False,
            ),
        }
        try:
            async for chunk_str in runner.stream(
                query=body.query,
                session_id=chat_session.id,
                user_id=str(user_id),
                history=body.history or None,
            ):
                if await request.is_disconnected():
                    break
                data = json.loads(chunk_str)
                yield {"event": data.get("event", "message"), "data": chunk_str}
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Once the SSE response has started, exception handlers can no
            # longer replace it with an HTTP error response. Isolate the
            # runtime failure here and report a stable terminal SSE event.
            logger.exception(
                "Agent stream failed for user_id={} session_id={}: {}",
                user_id,
                chat_session.id,
                exc,
            )
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "event": "error",
                        "code": "AGENT_STREAM_FAILED",
                        "message": t("agent.stream_failed"),
                    },
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(sse_event_publisher())

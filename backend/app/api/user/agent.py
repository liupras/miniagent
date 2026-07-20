#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Gemini Collaborator
# @date    : 2026-07-07
# @description: Authenticated Workplace agent and conversation endpoints.

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings
from app.core.i18n.i18n import t
from app.core.security.auth_permission import AuthPermission
from app.runtime.agent.agent_factory import AgentFactory
from app.runtime.conversation.service_conversation import ConversationService
from app.schemas.common import ApiResponse
from app.schemas.user.agent import AgentRequest, RenameSessionRequest

router = APIRouter()
current_user = AuthPermission.CurrentUser()


def _get_agent_factory(request: Request) -> AgentFactory:
    return request.app.state.container.agent_factory


def _get_service(request: Request) -> ConversationService:
    return request.app.state.container.conversation_service


async def _resolve_runner(body: AgentRequest, factory: AgentFactory):
    if body.agent_id is not None:
        return await factory.get_runner(body.agent_id)
    if body.agent_name:
        return await factory.get_runner_by_name(body.agent_name)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=t("agent.input_invalid"),
    )


async def _ensure_agent_access(
    request: Request,
    user_id: int,
    agent_id: int,
) -> None:
    relation_db = request.app.state.container.user_agent_relation_db
    if not await relation_db.user_has_agent(user_id, agent_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=t("agent.unauthorized"),
        )


async def _resolve_chat_session(
    service: ConversationService,
    user_id: int,
    agent_id: int,
    session_id: int | None,
):
    if session_id is None:
        return await service.create_user_session(user_id, agent_id)

    chat_session = await service.get_user_session(session_id, user_id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail=t("agent.session_not_found"))
    if chat_session.agent_id != agent_id:
        raise HTTPException(
            status_code=400,
            detail=t("agent.session_not_belong"),
        )
    return chat_session


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
    request: Request,
    user_id: int = Depends(current_user),
) -> ApiResponse:
    agents = await request.app.state.container.user_agent_relation_db.get_user_agents(
        user_id
    )
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
    service: ConversationService = Depends(_get_service),
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
    service: ConversationService = Depends(_get_service),
    user_id: int = Depends(current_user),
) -> ApiResponse:
    chat_session = await service.get_user_session(session_id, user_id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail=t("agent.session_not_found"))

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
    service: ConversationService = Depends(_get_service),
    user_id: int = Depends(current_user),
) -> ApiResponse:
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail=t("agent.title_not_empty"))
    if not await service.rename_user_session(session_id, user_id, title):
        raise HTTPException(status_code=404, detail=t("agent.session_not_found"))
    return ApiResponse(data={"session_id": session_id, "title": title})


@router.delete(
    "/sessions/{session_id}",
    response_model=ApiResponse,
    summary="Delete one of my sessions",
)
async def delete_my_session(
    session_id: int,
    service: ConversationService = Depends(_get_service),
    user_id: int = Depends(current_user),
) -> ApiResponse:
    if not await service.delete_user_session(session_id, user_id):
        raise HTTPException(status_code=404, detail=t("agent.session_not_found"))
    return ApiResponse()


@router.post("/invoke", response_model=ApiResponse, summary="Invoke an assigned agent")
async def agent_invoke(
    request: Request,
    body: AgentRequest,
    factory: AgentFactory = Depends(_get_agent_factory),
    service: ConversationService = Depends(_get_service),
    user_id: int = Depends(current_user),
) -> ApiResponse:
    runner = await _resolve_runner(body, factory)
    await _ensure_agent_access(request, user_id, runner.agent_id)
    chat_session = await _resolve_chat_session(
        service, user_id, runner.agent_id, body.session_id
    )
    answer = await runner.invoke(
        query=body.query,
        history=body.history or None,
        user_id=str(user_id),
        session_id=chat_session.id,
    )
    return ApiResponse(
        data={"answer": answer, "session_id": chat_session.id}
    )


@router.post("/stream", summary="Stream an assigned agent response over SSE")
async def agent_stream(
    request: Request,
    body: AgentRequest,
    factory: AgentFactory = Depends(_get_agent_factory),
    service: ConversationService = Depends(_get_service),
    user_id: int = Depends(current_user),
):
    runner = await _resolve_runner(body, factory)
    await _ensure_agent_access(request, user_id, runner.agent_id)
    chat_session = await _resolve_chat_session(
        service, user_id, runner.agent_id, body.session_id
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
        except Exception as exc:
            logger.exception(
                "Agent stream failed for user_id={} session_id={}: {}",
                user_id,
                chat_session.id,
                exc,
            )
            yield {
                "event": "error",
                "data": json.dumps(
                    {"event": "error", "message": "Agent response failed"},
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(sse_event_publisher())

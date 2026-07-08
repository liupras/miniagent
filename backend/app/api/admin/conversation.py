#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-08
# @description: FastAPI router — chat session and message management.

from fastapi import (
    Request,
    APIRouter,
    Depends,
    HTTPException,
)

from app.schemas.common import ApiResponse
from app.core.security.auth_permission import AuthPermission
from app.runtime.conversation.service_conversation import ConversationService

from app.schemas.admin.chat import(
    ChatSessionResponse,
    ChatSessionListResponse,
    ChatSessionListOut,
    ChatMessageResponse,
    ChatMessageListOut
)

# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────
router = APIRouter()

# ─────────────────────────────────────────────────────────────────
# Dependencies
# ─────────────────────────────────────────────────────────────────

def _get_service(request: Request) -> ConversationService:
    """
    Return the ConversationService singleton from ServiceContainer.
    """
    return request.app.state.container.conversation_service

_list   = AuthPermission.Permission("conversation:list")
_delete = AuthPermission.Permission("conversation:delete")


@router.get(
    "/sessions/{session_id}",
    response_model=ApiResponse[ChatSessionResponse],
    summary="Get a chat session"
)
async def get_chat_session(
    session_id: str,
    service: ConversationService = Depends(_get_service),
    caller_id: int = Depends(_list),
):
    """Get a chat session by session ID."""
    session = await service.get_session(session_id)
    if not session:
        raise HTTPException(404, detail="Chat session not found")
    
    response = ChatSessionResponse(
        id=session.id,
        session_id=session.session_id,
        title=session.title,
        user_id=session.user_id,
        agent_id=session.agent_id,
        message_count=session.message_count,
        total_tokens=session.total_tokens,
        created_at=session.created_at.isoformat() if session.created_at else None,
        updated_at=session.updated_at.isoformat() if session.updated_at else None
    )
    
    return ApiResponse(data=response)
    
@router.get(
    "/users/{user_id}/sessions",
    response_model=ApiResponse[ChatSessionListOut],
    summary="List chat sessions for a user"
)
async def list_chat_sessions(
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    service: ConversationService = Depends(_get_service),
    caller_id: int = Depends(_list),
):
    """List chat sessions for a user."""

    total, items = await service.list_sessions(
        user_id=user_id,
        page=page,
        page_size=page_size
    )
    
    session_items = []
    for item in items:
        session_items.append(ChatSessionListResponse(
            id=item.id,
            session_id=item.session_id,
            title=item.title,
            user_id=item.user_id,
            agent_id=item.agent_id,
            message_count=item.message_count,
            total_tokens=item.total_tokens,
            created_at=item.created_at.isoformat() if item.created_at else None,
            updated_at=item.updated_at.isoformat() if item.updated_at else None
        ))
    
    data = ChatSessionListOut(
        total=total,
        page=page,
        page_size=page_size,
        items=session_items
    )
    
    return ApiResponse(data=data)

@router.delete(
    "/sessions/{session_id}",
    response_model=ApiResponse[None],
    summary="Delete a chat session"
)
async def delete_chat_session(
    session_id: str,
    service: ConversationService = Depends(_get_service),
    caller_id: int = Depends(_delete),
):
    """Delete a chat session and all related messages."""

    await service.delete_session(session_id)    
    return ApiResponse()

    
@router.delete(
    "/messages/{message_id}",
    response_model=ApiResponse[None],
    summary="Delete a chat message"
)
async def delete_chat_message(
    message_id: int,
    service: ConversationService = Depends(_get_service),
    caller_id: int = Depends(_delete),
):
    """Delete a specific chat message."""

    await service.delete_message(message_id)        
    return ApiResponse()


@router.get(
    "/sessions/{session_id}/messages",
    response_model=ApiResponse[ChatMessageListOut],
    summary="Get chat messages for a session"
)
async def get_chat_messages(
    session_id: str,
    page: int = 1,
    page_size: int = 20,
    service: ConversationService = Depends(_get_service),
    caller_id: int = Depends(_list),
):
    """Get chat messages for a session."""

    total, items = await service.list_messages(
        session_id=session_id,
        page=page,
        page_size=page_size
    )
    
    message_items = []
    for item in items:
        message_items.append(ChatMessageResponse(
            id=item.id,
            session_id=item.session_id,
            role=item.role,
            content=item.content,
            created_at=item.created_at.isoformat() if item.created_at else None
        ))
    
    data = ChatMessageListOut(
        total=total,
        page=page,
        page_size=page_size,
        items=message_items
    )
    
    return ApiResponse(data=data)

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-08
# @description: Data Contract for chat

from typing import Optional, List
from pydantic import BaseModel

class ChatSessionResponse(BaseModel):
    """Response model for chat session."""
    id: int
    session_id: str
    title: Optional[str]
    user_id: int
    agent_id: Optional[int]
    message_count: int
    total_tokens: int
    created_at: str
    updated_at: str

class ChatSessionListResponse(BaseModel):
    """Response model for list of chat sessions."""
    id: int
    session_id: str
    title: Optional[str]
    user_id: int
    agent_id: Optional[int]
    message_count: int
    total_tokens: int
    created_at: str
    updated_at: str

class ChatSessionListOut(BaseModel):
    """Paginated list wrapper for chat sessions."""
    total: int
    page: int
    page_size: int
    items: List[ChatSessionListResponse]

class ChatMessageResponse(BaseModel):
    """Response model for chat message."""
    id: int
    session_id: int
    role: str
    content: str
    created_at: str

class ChatMessageListOut(BaseModel):
    """Paginated list wrapper for chat messages."""
    total: int
    page: int
    page_size: int
    items: List[ChatMessageResponse]
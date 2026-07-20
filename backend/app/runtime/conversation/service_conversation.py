#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-17
# @description: Chat service

# Maximum number of historical turns fetched from the DB per request.
# Each turn = 1 user message + 1 assistant message → up to 2 * DB_HISTORY_LIMIT rows.
DB_HISTORY_LIMIT: int = 40

# How many tokens to reserve for the model's *output*.
# Input context is capped at  max_tokens - CONTEXT_TOKEN_RESERVE.
CONTEXT_TOKEN_RESERVE: int = 500

from typing import Dict, List, Optional, Tuple
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from loguru import logger

from app.infra.db.database import ChatMessage, ChatSession
from app.repositories.async_chat import AsyncChatDatabase
from app.runtime.llm.func import truncate_messages, estimate_messages_tokens

from app.schemas.common import NotFoundError
class SessionNotFoundError(NotFoundError):
    def __init__(self, session_id: str):
        super().__init__("Session", session_id)

class MessageNotFoundError(NotFoundError):
    def __init__(self, message_id: int):
        super().__init__("Message", message_id)


class ConversationService:

    def __init__(
        self,
        chat_db: AsyncChatDatabase,
    ):
        self._chat_db = chat_db

    async def save_message(
        self,
        user_id: str,
        agent_id: int,
        session_id: Optional[int],
        role: str,
        content: str,        
    ) -> int:
        
        res = await self._chat_db.save_message(
            user_id=user_id,
            agent_id=agent_id,
            session_id=session_id,
            role=role,
            content=content,
        )
        return res
    
    async def _load_db_history(
        self,
        user_id: str,
        session_id: int,
    ) -> List[Dict[str, str]]:
        """
        Fetch recent conversation turns from the database.

        get_chat_history_latest() returns rows in *descending* order
        (newest first).  We reverse them so the list is chronological
        (oldest → newest) before returning.

        Note: the current user message has already been written to the DB
        before this helper is called, so we exclude the last row (which is
        the message we just saved) to avoid duplicating it in history.
        """
        rows = await self._chat_db.get_chat_history_latest(
            user_id=user_id,
            session_id=session_id,
            limit=DB_HISTORY_LIMIT + 1,  # +1 to cover the just-saved user msg
        )
        # Drop the first row (newest = the user message we just persisted).
        rows = rows[1:]
        # Desc order.
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    async def build_messages(
        self,
        query: str,
        system_prompt:str,
        max_tokens:int,
        history: Optional[List[Dict[str, str]]],
        user_id: Optional[str],
        session_id: Optional[int],
    ) -> List[BaseMessage]:
        """
        Build the LangChain message list for a single turn.

        Priority rules
        ──────────────
        1. If caller passed an explicit ``history`` list, use it as-is
           (backward-compatible with stateless callers).
        2. If user_id + session_id are provided and no explicit history is
           given, load history from the database.
        3. Merge: [SystemMessage] + history + [HumanMessage(query)].
        4. Truncate to fit within the LLM context budget.

        Layout after truncation:
            SystemMessage(system_prompt)
            … history messages (oldest → newest, pruned from the middle) …
            HumanMessage(query)
        """
        # ── Resolve history source ─────────────────────────────────────────
        if history is not None:
            # Caller supplied explicit history — use it directly.
            resolved_history = history
        elif user_id and session_id:
            # Load from DB (already saved the current user msg, so skip it).
            resolved_history = await self._load_db_history(user_id, session_id)
        else:
            resolved_history = []

        # ── Build raw dict list for token budgeting ────────────────────────
        system_dict = {"role": "system", "content": system_prompt}
        query_dict = {"role": "user", "content": query}

        # History comes in reverse-chronological
        raw_msgs = (
            [system_dict]
            + [query_dict]
            + list(resolved_history)
        )

        # Leave CONTEXT_TOKEN_RESERVE tokens for the model's output.
        input_budget = max(max_tokens - CONTEXT_TOKEN_RESERVE, 512)
        truncated = truncate_messages(raw_msgs, input_budget)

        # ── Convert to LangChain message objects ───────────────────────────
        msgs: List[BaseMessage] = []
        for turn in truncated:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "system":
                msgs.append(SystemMessage(content=content))
            elif role == "user":
                msgs.append(HumanMessage(content=content))
            elif role == "assistant":
                msgs.append(AIMessage(content=content))
        
        total_tokens = estimate_messages_tokens(
            [{"role": t.get("role", ""), "content": t.get("content", "")} for t in truncated]
        )
        logger.debug(
            f"[ConversationService] context — "
            f"{len(msgs)} messages, ~{total_tokens} tokens "
            f"(budget={input_budget})."
        )
        return msgs
    

    async def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Get a chat session by session ID."""
        return await self._chat_db.get_session_by_id(session_id)

    async def create_user_session(self, user_id: int, agent_id: int) -> ChatSession:
        return await self._chat_db.create_user_session(user_id, agent_id)

    async def get_user_session(
        self,
        session_id: int,
        user_id: int,
    ) -> Optional[ChatSession]:
        return await self._chat_db.get_user_session(session_id, user_id)

    async def list_user_sessions(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
        query: Optional[str] = None,
    ) -> Tuple[int, List[ChatSession]]:
        return await self._chat_db.list_user_sessions(
            user_id, page, page_size, query
        )

    async def list_user_messages(
        self,
        session_id: int,
        user_id: int,
        page: int = 1,
        page_size: int = 200,
    ) -> Tuple[int, List[ChatMessage]]:
        return await self._chat_db.list_user_messages(
            session_id, user_id, page, page_size
        )

    async def rename_user_session(
        self,
        session_id: int,
        user_id: int,
        title: str,
    ) -> bool:
        return await self._chat_db.rename_user_session(
            session_id, user_id, title
        )

    async def delete_user_session(self, session_id: int, user_id: int) -> bool:
        return await self._chat_db.delete_user_session(session_id, user_id)

    async def list_sessions(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[int, List[ChatSession]]:
        """List chat sessions for a user."""
        return await self._chat_db.list_sessions(user_id, page, page_size)

    async def list_messages(
        self,
        session_id: int,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[int, List[ChatMessage]]:
        """List chat messages for a session."""
        return await self._chat_db.list_messages(session_id, page, page_size)

    async def delete_session(self, session_id: int) -> bool:
        """Delete a specific chat session."""
        res = await self._chat_db.delete_session(session_id)
        if not res:
            raise SessionNotFoundError(session_id)
        return res
    
    async def delete_message(self, message_id: int) -> bool:
        """Delete a specific chat message."""
        res = await self._chat_db.delete_message(message_id)
        if not res:
            raise MessageNotFoundError(message_id)
        return res

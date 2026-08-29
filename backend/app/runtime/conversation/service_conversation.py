#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-17
# @description: Chat service

# Maximum number of historical turns fetched from the DB per request.
# Each turn = 1 user message + 1 assistant message → up to 2 * DB_HISTORY_LIMIT rows.
DB_HISTORY_LIMIT: int = 40

# Provider chat templates and tokenizer estimates introduce a small amount of
# overhead that is not represented by the message content itself.
TOKEN_SAFETY_MARGIN: int = 512

from typing import Dict, List, Optional, Tuple
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from app.core.logger_config import get_logger

logger = get_logger(__name__)
from app.infra.db.database import ChatMessage, ChatSession
from app.repositories.async_chat import AsyncChatDatabase
from app.runtime.conversation.title_generator import (
    ConversationTitleGenerator,
    TitleGenerationError,
    title_generator,
)
from app.runtime.llm.func import truncate_messages
from app.utils.tokens import TokenCounter, sanitize_chat_messages

from app.schemas.exceptions import NotFoundError
class SessionNotFoundError(NotFoundError):
    def __init__(self, session_id: str):
        super().__init__("Session", session_id)

class MessageNotFoundError(NotFoundError):
    def __init__(self, message_id: int):
        super().__init__("Message", message_id)


def calculate_input_budget(
    context_window_tokens: int,
    max_output_tokens: int,
    safety_margin_tokens: int = TOKEN_SAFETY_MARGIN,
) -> int:
    """Return the token budget available to input messages."""
    if context_window_tokens <= 0:
        raise ValueError("context_window_tokens must be greater than zero")
    if max_output_tokens <= 0:
        raise ValueError("max_output_tokens must be greater than zero")
    if safety_margin_tokens < 0:
        raise ValueError("safety_margin_tokens must not be negative")

    input_budget = (
        context_window_tokens
        - max_output_tokens
        - safety_margin_tokens
    )
    if input_budget <= 0:
        raise ValueError(
            "No input token budget remains after reserving max_output_tokens "
            "and the safety margin"
        )
    return input_budget


class ConversationService:

    def __init__(
        self,
        chat_db: AsyncChatDatabase,
        conversation_title_generator: Optional[ConversationTitleGenerator] = None,
    ):
        self._chat_db = chat_db
        self._title_generator = conversation_title_generator or title_generator

    async def _title_for_message(
        self,
        session_id: Optional[int],
        role: str,
        content: str,
    ) -> Optional[str]:
        """Generate a title only when the user message belongs to an untitled session."""
        if role != "user":
            return None

        if session_id is not None:
            chat_session = await self._chat_db.get_session_by_id(session_id)
            if chat_session is not None and chat_session.title:
                return None

        try:
            return self._title_generator.generate(content)
        except TitleGenerationError as exc:
            # Invalid title input/configuration is a known, non-critical
            # failure: persisting the conversation takes precedence.
            logger.warning(
                "Conversation title generation failed; using default title: {}",
                exc,
            )
            return self._title_generator.config.default_title

    async def save_message(
        self,
        user_id: str,
        agent_id: int,
        session_id: Optional[int],
        role: str,
        content: str,        
    ) -> int:
        session_title = await self._title_for_message(
            session_id=session_id,
            role=role,
            content=content,
        )
        res = await self._chat_db.save_message(
            user_id=user_id,
            agent_id=agent_id,
            session_id=session_id,
            role=role,
            content=content,
            session_title=session_title,
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
        # Drop the first row (newest = the user message just persisted), then
        # convert the remaining DB rows from newest-first to chronological.
        history_rows = reversed(rows[1:])
        return [
            {"role": r["role"], "content": r["content"]}
            for r in history_rows
        ]

    @staticmethod
    def _normalize_explicit_history(
        history: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """Copy chronological dialogue history and discard unsupported roles."""
        normalized: List[Dict[str, str]] = []
        for message in history:
            role = str(message.get("role", "")).lower()
            if role not in {"user", "assistant"}:
                logger.warning(
                    "[ConversationService] Ignoring unsupported explicit "
                    "history role: {}",
                    role or "<empty>",
                )
                continue
            normalized.append({
                "role": role,
                "content": str(message.get("content", "")),
            })
        return normalized

    async def build_messages(
        self,
        query: str,
        system_prompt:str,
        context_window_tokens: int,
        max_output_tokens: int,
        model_name: str,
        history: Optional[List[Dict[str, str]]],
        user_id: Optional[str],
        session_id: Optional[int],
    ) -> List[BaseMessage]:
        """
        Build the LangChain message list for a single turn.

        Priority rules
        ──────────────
        1. If caller passed an explicit chronological ``history`` list, copy
           and normalize its user/assistant messages.
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
            resolved_history = self._normalize_explicit_history(history)
        elif user_id and session_id:
            # Load from DB (already saved the current user msg, so skip it).
            resolved_history = await self._load_db_history(user_id, session_id)
        else:
            resolved_history = []

        # ── Build raw dict list for token budgeting ────────────────────────
        system_dict = {"role": "system", "content": system_prompt}
        query_dict = {"role": "user", "content": query}

        # One canonical order is used by every history source.
        raw_msgs = (
            [system_dict]
            + list(resolved_history)
            + [query_dict]
        )

        input_budget = calculate_input_budget(
            context_window_tokens=context_window_tokens,
            max_output_tokens=max_output_tokens,
        )
        token_counter = TokenCounter(model=model_name)
        truncated = truncate_messages(
            raw_msgs,
            input_budget,
            token_counter=token_counter,
        )

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
        
        provider_messages = sanitize_chat_messages(
            [
                {"role": t.get("role", ""), "content": t.get("content", "")}
                for t in truncated
            ]
        )
        # This is a preliminary context before AgentLLM injects its tool
        # prompt. Keep this pass lightweight; AgentLLM performs the optional
        # near-limit tokenizer pass on the final provider payload.
        total_tokens = token_counter.count_messages(provider_messages)
        logger.debug(
            f"[ConversationService] context — "
            f"{len(msgs)} messages, ~{total_tokens} payload tokens "
            f"(input_budget={input_budget}, "
            f"model={model_name}, "
            f"context_window={context_window_tokens}, "
            f"max_output={max_output_tokens}, "
            f"safety_margin={TOKEN_SAFETY_MARGIN})."
        )
        return msgs
    

    async def get_session(self, session_id: str) -> ChatSession:
        """Get a chat session or raise a stable application error."""
        session = await self._chat_db.get_session_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session

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

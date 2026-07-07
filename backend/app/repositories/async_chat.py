#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: Chat Database Management (Asynchronous Version)

from datetime import datetime
from typing import List, Dict, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.async_base import AsyncBaseDatabase
from app.infra.db.database import ChatSession, ChatMessage

from app.runtime.conversation.title_generator import title_generator

class AsyncChatDatabase(AsyncBaseDatabase):

    async def _get_or_create_session(self, session: AsyncSession, user_id: str, session_id: str) -> ChatSession:
        """Internal asynchronous method: Get or create a chat session"""

        stmt = select(ChatSession).filter_by(user_id=user_id, session_id=session_id)
        result = await session.execute(stmt)
        chat_session = result.scalars().first()

        if chat_session:
            chat_session.updated_at = datetime.now()
            return chat_session

        chat_session = ChatSession(
            user_id=user_id,
            session_id=session_id,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        session.add(chat_session)
        await session.flush()  # Asynchronous retrieval of auto-incrementing ID

        return chat_session

    async def save_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,        
    ) -> int:

        async with self.get_session() as session:
            chat_session = await self._get_or_create_session(session, user_id, session_id)

            # A title will only be generated using the current content if the role is "user" and the current session does not yet have a title.
            if role == "user" and not chat_session.title:
                try:
                    generated_title = title_generator.generate(content)
                    chat_session.title = generated_title
                except Exception as e:                    
                    from loguru import logger
                    logger.error(f"Failed to generate title for session {session_id}: {e}")
                    chat_session.title="..."

            message = ChatMessage(
                user_id=user_id,
                session_id=chat_session.id,
                role=role,
                content=content,
                created_at=datetime.now()
            )

            session.add(message)
            await session.flush()

            return message.id

    async def get_chat_history_latest(
        self,
        user_id: str,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict]:

        async with self.get_session() as session:
            stmt = (
                select(ChatMessage)
                .join(ChatSession)
                .filter(
                    ChatSession.user_id == user_id,
                    ChatSession.session_id == session_id
                )
                .order_by(ChatMessage.created_at.desc())
            )

            if limit:
                stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            messages = result.scalars().all()

            return [
                {
                    "role": m.role,
                    "content": m.content,                    
                    "created_at": m.created_at
                }
                for m in messages
            ]

    async def get_user_sessions(self, user_id: str) -> List[Dict]:

        async with self.get_session() as session:
            stmt = (
                select(
                    ChatSession.session_id,
                    ChatSession.created_at,
                    ChatSession.updated_at,
                    func.count(ChatMessage.id).label("message_count")
                )
                .outerjoin(ChatMessage)
                .filter(ChatSession.user_id == user_id)
                .group_by(ChatSession.id)
                .order_by(ChatSession.updated_at.desc())
            )

            result = await session.execute(stmt)
            sessions = result.all()

            return [
                {
                    "session_id": s.session_id,
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                    "message_count": s.message_count
                }
                for s in sessions
            ]

    async def delete_session(self, user_id: str, session_id: str) -> bool:

        async with self.get_session() as session:
            # First check if it exists
            stmt = select(ChatSession).filter_by(user_id=user_id, session_id=session_id)
            result = await session.execute(stmt)
            chat_session = result.scalars().first()

            if not chat_session:
                return False

            # Execute deletion
            await session.delete(chat_session)
            return True
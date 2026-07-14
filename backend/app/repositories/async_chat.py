#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: Chat Database Management (Asynchronous Version)

from datetime import datetime
from typing import List, Dict, Optional,Tuple

from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.async_base import AsyncBaseDatabase
from app.infra.db.database import ChatSession, ChatMessage

from app.runtime.conversation.title_generator import title_generator

class AsyncChatDatabase(AsyncBaseDatabase):

    async def _get_or_create_session(self, session: AsyncSession, user_id: str, agent_id:int,session_id: Optional[int]) -> ChatSession:
        """Internal asynchronous method: Get or create a chat session"""

        if session_id:
            stmt = select(ChatSession).filter_by(id=session_id)
            result = await session.execute(stmt)
            chat_session = result.scalars().first()

            if chat_session:
                chat_session.updated_at = datetime.now()
                return chat_session

        chat_session = ChatSession(
            user_id=user_id,
            agent_id = agent_id,
            id=session_id,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        session.add(chat_session)
        await session.flush()  # Asynchronous retrieval of auto-incrementing ID

        return chat_session

    async def save_message(
        self,
        user_id: str,
        agent_id: int,
        session_id: Optional[int],
        role: str,
        content: str,        
    ) -> int:

        async with self.get_session() as session:
            chat_session = await self._get_or_create_session(session, user_id, agent_id,session_id)

            # 1. A title will only be generated using the current content if the role is "user" and the current session does not yet have a title.
            if role == "user" and not chat_session.title:
                try:
                    generated_title = title_generator.generate(content)
                    chat_session.title = generated_title
                except Exception as e:                    
                    from loguru import logger
                    logger.error(f"Failed to generate title for session {session_id}: {e}")
                    chat_session.title="..."

            # 2. Create and save new messages
            message = ChatMessage(
                session_id=chat_session.id,
                role=role,
                content=content,
                created_at=datetime.now()
            )

            session.add(message)
            await session.flush()

            # 3. Count the total number of real messages in this session.
            count_stmt = select(func.count(ChatMessage.id)).filter_by(session_id=chat_session.id)
            count_result = await session.execute(count_stmt)
            total_messages = count_result.scalar() or 0

            # 4. Synchronize updates to the session table
            chat_session.message_count = total_messages
            chat_session.updated_at = datetime.now()

            return message.id

    async def get_chat_history_latest(
        self,
        user_id: str,
        session_id: int,
        limit: Optional[int] = None
    ) -> List[Dict]:

        async with self.get_session() as session:
            stmt = (
                select(ChatMessage)
                .join(ChatSession)
                .filter(
                    ChatSession.user_id == user_id,
                    ChatSession.id == session_id
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
                    ChatSession.id,
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
                    "session_id": s.id,
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                    "message_count": s.message_count
                }
                for s in sessions
            ]
        
    async def get_session_by_id(self, session_id: int) -> Optional[ChatSession]:
        """Get a chat session by session ID."""
        async with self.get_session() as session:
            stmt = select(ChatSession).where(ChatSession.id == session_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_sessions(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[int, List[ChatSession]]:
        """List chat sessions for a user."""
        async with self.get_session() as session:
            # Get total count
            count_query = select(func.count(ChatSession.id)).where(ChatSession.user_id == user_id)
            total: int = (await session.execute(count_query)).scalar_one()

            # Get paginated results
            offset = (page - 1) * page_size
            query = select(ChatSession).where(ChatSession.user_id == user_id).order_by(ChatSession.created_at.desc())
            result = await session.execute(query.offset(offset).limit(page_size))
            sessions = result.scalars().all()

            return total, list(sessions)

    async def list_messages(
        self,
        session_id: int,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[int, List[ChatMessage]]:
        """List chat messages for a session."""
        async with self.get_session() as session:
            # Get total count
            count_query = select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session_id)
            total: int = (await session.execute(count_query)).scalar_one()

            # Get paginated results
            offset = (page - 1) * page_size
            query = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc())
            result = await session.execute(query.offset(offset).limit(page_size))
            messages = result.scalars().all()

            return total, list(messages)

    async def delete_session(self, session_id: int) -> bool:
        """Delete a chat session and all related messages."""
        async with self.get_session() as session:
            # First delete all messages in the session
            await session.execute(
                delete(ChatMessage).where(ChatMessage.session_id == session_id)
            )
            
            # Then delete the session itself
            result = await session.execute(
                delete(ChatSession).where(ChatSession.id == session_id)
            )
            
            return result.rowcount > 0
        
    async def delete_message(self, message_id: int) -> bool:
        """Delete a specific chat message."""
        async with self.get_session() as session:
            result = await session.execute(
                delete(ChatMessage).where(ChatMessage.id == message_id)
            )
            return result.rowcount > 0
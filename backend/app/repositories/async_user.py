#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: User Database Management (Asynchronous)

from datetime import datetime
from typing import Optional, Dict, List
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.infra.db.async_base import AsyncBaseDatabase
from app.infra.db.database import User
from app.core.security import bcrypt_hash, verify_bcrypt

class AsyncUserDatabase(AsyncBaseDatabase):

    def _hash_password(self, password: str) -> str:
        """Maintain synchronization, as encryption is typically a CPU-intensive operation."""
        return bcrypt_hash(password)

    async def _get_user_by_username(self, session, username: str) -> Optional[User]:
        """Helper: query User by username field."""
        result = await session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def create_user(self, username: str, password: str) -> bool:

        async with self.get_session() as session:
            existing_user = await self._get_user_by_username(session, username)
            if existing_user:
                return False

            user = User(
                username=username,
                password_hash=self._hash_password(password),
                created_at=datetime.now()
            )

            session.add(user)
            # The context manager for async_base will automatically handle commits.
            return True

    async def verify_user(self, username: str, password: str) -> bool:
        """Asynchronous user authentication"""
        async with self.get_session() as session:
            user = await self._get_user_by_username(session, username)

            if not user or not user.is_active:
                return False

            # verify_bcrypt is a synchronous salted verification.
            if not verify_bcrypt(password, user.password_hash):
                return False

            user.last_login = datetime.now()
            return True

    async def get_user_info(self, username: str) -> Optional[Dict]:

        async with self.get_session() as session:

            stmt = select(User).options(selectinload(User.roles)).where(User.username == username)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                return None

            return {
                "id": user.id,
                "username": user.username,
                "nickname": user.nickname,
                "avatar": user.avatar,
                "roles": [r.code for r in user.roles] if user.roles else ["common"],
                "created_at": user.created_at,
                "last_login": user.last_login,
                "is_active": user.is_active,
            }

    async def update_password(self, username: str, old_password: str, new_password: str) -> bool:

        if not await self.verify_user(username, old_password):
            return False

        async with self.get_session() as session:
            user = await self._get_user_by_username(session, username)
            if user:
                user.password_hash = self._hash_password(new_password)
                return True
            return False

    async def deactivate_user(self, username: str) -> bool:

        async with self.get_session() as session:
            user = await self._get_user_by_username(session, username)
            if not user:
                return False

            user.is_active = False
            return True

    async def get_all_users(self) -> List[Dict]:

        async with self.get_session() as session:
            stmt = select(User).options(selectinload(User.roles)).order_by(User.created_at.desc())
            result = await session.execute(stmt)
            users = result.scalars().all()

            return [
                {
                    "id": u.id,
                    "username": u.username,
                    "nickname": u.nickname,
                    "avatar": u.avatar,
                    "roles": [r.name for r in u.roles] if u.roles else ["common"],
                    "created_at": u.created_at,
                    "last_login": u.last_login,
                    "is_active": u.is_active,
                }
                for u in users
            ]

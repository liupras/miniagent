#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: User Database Management (Asynchronous)

from datetime import datetime
from typing import Optional, Dict,List
from sqlalchemy import select,func
from sqlalchemy.orm import selectinload

from app.infra.db.async_base import AsyncBaseDatabase
from app.infra.db.database import User
from app.core.security import bcrypt_hash, verify_bcrypt
from app.schemas.admin.user import UserListParams

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

            stmt = (
                select(User)
                .options(
                    selectinload(User.roles)
                )
                .where(User.username == username)
            )
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
                #"permissions": permissions or [],
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
        
    async def get_options(
        self,
        is_active: bool | None = True
    ) -> list[User]:

        async with self.get_session() as session:

            stmt = select(User).order_by(User.username)

            if is_active is not None:
                stmt = stmt.where(User.is_active == is_active)

            result = await session.execute(stmt)

            return list(result.scalars().all())
        
    async def list_users(
        self,
        params: UserListParams
    ) -> tuple[list[User], int]:
        
        async with self._user_db.get_session() as session:
            stmt = select(User).options(
                selectinload(User.roles)
            )

            if params.username:
                stmt = stmt.where(User.username.ilike(f"%{params.username}%"))
            if params.is_active is not None:
                stmt = stmt.where(User.is_active == params.is_active)

            total: int = (
                await session.execute(
                    select(func.count()).select_from(stmt.subquery())
                )
            ).scalar_one()

            offset = (params.page - 1) * params.page_size
            stmt = (
                stmt.order_by(User.created_at.desc())
                .offset(offset)
                .limit(params.page_size)
            )
            rows: List[User] = list((await session.execute(stmt)).scalars().all())

            return rows, total
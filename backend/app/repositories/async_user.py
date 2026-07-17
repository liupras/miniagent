#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: Asynchronous persistence operations for users and their role bindings.

from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from app.core.security.hash import bcrypt_hash, verify_bcrypt
from app.infra.db.async_base import AsyncBaseDatabase
from app.infra.db.database import Role, User, UserRoleRelation
from app.schemas.admin.user import UserListParams


class AsyncUserDatabase(AsyncBaseDatabase):
    def _hash_password(self, password: str) -> str:
        return bcrypt_hash(password)

    async def _get_user_by_username(self, session, username: str) -> Optional[User]:
        result = await session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> Optional[User]:
        async with self.get_session() as session:
            result = await session.execute(
                select(User)
                .options(selectinload(User.roles))
                .where(User.id == user_id)
            )
            return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[User]:
        async with self.get_session() as session:
            result = await session.execute(
                select(User)
                .options(selectinload(User.roles))
                .where(User.username == username)
            )
            return result.scalar_one_or_none()

    async def create_user(
        self,
        username: str,
        password: str,
        nickname: str | None = None,
        avatar: str | None = None,
        is_active: bool = True,
        role_ids: list[int] | None = None,
    ) -> Optional[User]:
        async with self.get_session() as session:
            if await self._get_user_by_username(session, username):
                return None

            roles: list[Role] = []
            if role_ids:
                roles = list(
                    (await session.execute(select(Role).where(Role.id.in_(set(role_ids)))))
                    .scalars()
                    .all()
                )

            user = User(
                username=username,
                password_hash=self._hash_password(password),
                nickname=nickname,
                avatar=avatar,
                is_active=is_active,
                created_at=datetime.now(),
                roles=roles,
            )
            session.add(user)
            await session.flush()
            await session.refresh(user, attribute_names=["roles"])
            return user

    async def verify_user(self, username: str, password: str) -> bool:
        async with self.get_session() as session:
            user = await self._get_user_by_username(session, username)
            if not user or not user.is_active or not verify_bcrypt(password, user.password_hash):
                return False
            user.last_login = datetime.now()
            return True

    async def get_user_info(self, username: str) -> Optional[Dict]:
        user = await self.get_by_username(username)
        if not user:
            return None
        return {
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
            "avatar": user.avatar,
            "roles": [role.code for role in user.roles],
            "created_at": user.created_at,
            "last_login": user.last_login,
            "is_active": user.is_active,
        }

    async def update_password(self, username: str, old_password: str, new_password: str) -> bool:
        if not await self.verify_user(username, old_password):
            return False
        user = await self.get_by_username(username)
        return bool(user and await self.set_password(user.id, new_password))

    async def set_password(self, user_id: int, password: str) -> bool:
        async with self.get_session() as session:
            user = await session.get(User, user_id)
            if not user:
                return False
            user.password_hash = self._hash_password(password)
            return True

    async def deactivate_user(self, username: str) -> bool:
        async with self.get_session() as session:
            user = await self._get_user_by_username(session, username)
            if not user:
                return False
            user.is_active = False
            return True

    async def get_options(self, is_active: bool | None = True) -> list[User]:
        async with self.get_session() as session:
            stmt = select(User).order_by(User.username)
            if is_active is not None:
                stmt = stmt.where(User.is_active == is_active)
            return list((await session.execute(stmt)).scalars().all())

    async def list_users(self, params: UserListParams) -> tuple[list[User], int]:
        async with self.get_session() as session:
            stmt = select(User).options(selectinload(User.roles))
            if params.keyword:
                like = f"%{params.keyword}%"
                stmt = stmt.where(or_(User.username.ilike(like), User.nickname.ilike(like)))
            if params.username:
                stmt = stmt.where(User.username.ilike(f"%{params.username}%"))
            if params.is_active is not None:
                stmt = stmt.where(User.is_active == params.is_active)
            if params.role_id is not None:
                stmt = stmt.join(UserRoleRelation).where(UserRoleRelation.role_id == params.role_id)

            total = (
                await session.execute(select(func.count()).select_from(stmt.subquery()))
            ).scalar_one()
            stmt = (
                stmt.order_by(User.created_at.desc(), User.id.desc())
                .offset((params.page - 1) * params.page_size)
                .limit(params.page_size)
            )
            return list((await session.execute(stmt)).scalars().unique().all()), total

    async def update_fields(self, user_id: int, data: dict) -> Optional[User]:
        async with self.get_session() as session:
            user = await session.get(User, user_id)
            if not user:
                return None
            for field, value in data.items():
                setattr(user, field, value)
            await session.flush()
            return user

    async def set_roles(self, user_id: int, role_ids: list[int]) -> Optional[User]:
        async with self.get_session() as session:
            user = (
                await session.execute(
                    select(User).options(selectinload(User.roles)).where(User.id == user_id)
                )
            ).scalar_one_or_none()
            if not user:
                return None
            roles = list(
                (await session.execute(select(Role).where(Role.id.in_(set(role_ids)))))
                .scalars()
                .all()
            ) if role_ids else []
            user.roles = roles
            await session.flush()
            await session.refresh(user, attribute_names=["roles"])
            return user

    async def delete_user(self, user_id: int) -> bool:
        async with self.get_session() as session:
            user = await session.get(User, user_id)
            if not user:
                return False
            await session.delete(user)
            return True

    async def existing_role_ids(self, role_ids: list[int]) -> set[int]:
        if not role_ids:
            return set()
        async with self.get_session() as session:
            return set((await session.execute(select(Role.id).where(Role.id.in_(set(role_ids))))).scalars())

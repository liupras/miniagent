#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-30
# @description: Business logic for administrative user management.

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.service_container import ServiceContainer

from app.infra.db.database import User
from app.schemas.admin.user import UserCreate, UserListParams, UserOptionItem, UserOut, UserUpdate
from app.schemas.common import AlreadyExistsError, NotFoundError, PageResult


class UserNotFoundError(NotFoundError):
    def __init__(self, entity_id: Any):
        super().__init__("User", entity_id)


class UserAlreadyExistsError(AlreadyExistsError):
    def __init__(self, entity_id: Any):
        super().__init__("User", entity_id)


class RoleNotFoundError(NotFoundError):
    def __init__(self, entity_id: Any):
        super().__init__("Role", entity_id)


def _to_user_out(user: User, permissions: list[str] | None = None) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        nickname=user.nickname,
        avatar=user.avatar,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login=user.last_login,
        failed_login_attempts=user.failed_login_attempts or 0,
        locked_until=user.locked_until,
        is_locked=bool(user.locked_until and user.locked_until > datetime.now()),
        roles=[role.code for role in user.roles],
        permissions=permissions or [],
    )


class UserService:
    def __init__(self, container:ServiceContainer) -> None:
        self._user_db = container.user_db
        self._menu_db = container.menu_db
        self._auth = container.auth

    async def get_options(self, is_active: Optional[bool] = True) -> list[UserOptionItem]:
        return [UserOptionItem.model_validate(user) for user in await self._user_db.get_options(is_active)]

    async def list_users(self, params: UserListParams) -> PageResult[UserOut]:
        rows, total = await self._user_db.list_users(params)
        return PageResult(
            total=total,
            page=params.page,
            page_size=params.page_size,
            data=[_to_user_out(row) for row in rows],
        )

    async def get_user_by_id(self, user_id: int) -> UserOut:
        user = await self._user_db.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        permissions = sorted(await self._menu_db.get_user_resource_codes(user.id))
        return _to_user_out(user, permissions)

    async def get_user(self, username: str) -> UserOut:
        user = await self._user_db.get_by_username(username)
        if not user:
            raise UserNotFoundError(username)
        permissions = sorted(await self._menu_db.get_user_resource_codes(user.id))
        return _to_user_out(user, permissions)

    async def create(self, payload: UserCreate) -> UserOut:
        await self._validate_roles(payload.role_ids)
        if await self._user_db.get_by_username(payload.username):
            raise UserAlreadyExistsError(payload.username)
        user = await self._user_db.create_user(**payload.model_dump())
        if user is None:
            raise UserAlreadyExistsError(payload.username)
        return _to_user_out(user)

    async def update(self, user_id: int, payload: UserUpdate) -> UserOut:
        current = await self._user_db.get_by_id(user_id)
        if not current:
            raise UserNotFoundError(user_id)
        data = payload.model_dump(exclude_unset=True)
        if data.get("username") and data["username"] != current.username:
            if await self._user_db.get_by_username(data["username"]):
                raise UserAlreadyExistsError(data["username"])
        await self._user_db.update_fields(user_id, data)
        self._invalidate(user_id)
        return _to_user_out(await self._require(user_id))

    async def assign_roles(self, user_id: int, role_ids: list[int]) -> UserOut:
        await self._validate_roles(role_ids)
        user = await self._user_db.set_roles(user_id, role_ids)
        if not user:
            raise UserNotFoundError(user_id)
        self._invalidate(user_id)
        return _to_user_out(user)

    async def reset_password(self, user_id: int, password: str) -> None:
        if not await self._user_db.set_password(user_id, password):
            raise UserNotFoundError(user_id)

    async def unlock(self, user_id: int) -> None:
        if not await self._user_db.unlock_user(user_id):
            raise UserNotFoundError(user_id)

    async def delete(self, user_id: int) -> None:
        if not await self._user_db.delete_user(user_id):
            raise UserNotFoundError(user_id)
        self._invalidate(user_id)

    async def verify_user(self, username: str, password: str) -> bool:
        return await self._user_db.verify_user(username, password)

    async def authenticate(self, username: str, password: str):
        from app.core.config import settings

        return await self._user_db.authenticate(
            username,
            password,
            max_failed_attempts=settings.login_max_failed_attempts,
            lock_duration_minutes=settings.login_lock_duration_minutes,
        )

    async def _validate_roles(self, role_ids: list[int]) -> None:
        requested = set(role_ids)
        missing = requested - await self._user_db.existing_role_ids(role_ids)
        if missing:
            raise RoleNotFoundError(min(missing))

    async def _require(self, user_id: int) -> User:
        user = await self._user_db.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        return user

    def _invalidate(self, user_id: int) -> None:
        if self._auth:
            self._auth.invalidate(user_id)

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-17
# @description: Business logic for role management and menu grants.

from __future__ import annotations

from typing import Any

from app.infra.db.database import Role
from app.schemas.admin.permission import RoleCreate, RoleMenuUpdate, RoleOut, RoleUpdate
from app.schemas.common import AlreadyExistsError, NotFoundError, PageResult


class RoleNotFoundError(NotFoundError):
    def __init__(self, entity_id: Any):
        super().__init__("Role", entity_id)


class RoleAlreadyExistsError(AlreadyExistsError):
    def __init__(self, entity_id: Any):
        super().__init__("Role", entity_id)


class MenuNotFoundError(NotFoundError):
    def __init__(self, entity_id: Any):
        super().__init__("Menu", entity_id)


def _to_out(role: Role, user_count: int = 0) -> RoleOut:
    return RoleOut(
        id=role.id,
        code=role.code,
        name=role.name,
        description=role.description,
        is_super=role.is_super,
        menu_ids=sorted(menu.id for menu in role.menus),
        user_count=user_count,
    )


class RoleService:
    def __init__(self, container) -> None:
        self._db = container.role_db
        self._auth = container.auth

    async def list(self, page: int, page_size: int, keyword: str | None) -> PageResult[RoleOut]:
        rows, total = await self._db.list_roles(page, page_size, keyword)
        return PageResult(total=total, page=page, page_size=page_size, data=[_to_out(role, count) for role, count in rows])

    async def get(self, role_id: int) -> RoleOut:
        role = await self._db.get_by_id(role_id)
        if not role:
            raise RoleNotFoundError(role_id)
        return _to_out(role)

    async def create(self, payload: RoleCreate) -> RoleOut:
        if await self._db.get_by_code(payload.code):
            raise RoleAlreadyExistsError(payload.code)
        await self._validate_menus(payload.menu_ids)
        data = payload.model_dump(exclude={"menu_ids"})
        return _to_out(await self._db.create_role(data, payload.menu_ids))

    async def update(self, role_id: int, payload: RoleUpdate) -> RoleOut:
        current = await self._db.get_by_id(role_id)
        if not current:
            raise RoleNotFoundError(role_id)
        data = payload.model_dump(exclude_unset=True)
        if data.get("code") and data["code"] != current.code and await self._db.get_by_code(data["code"]):
            raise RoleAlreadyExistsError(data["code"])
        await self._db.update_fields(role_id, data)
        await self._invalidate_role_users(role_id)
        return await self.get(role_id)

    async def set_menus(self, role_id: int, payload: RoleMenuUpdate) -> RoleOut:
        await self._validate_menus(payload.menu_ids)
        role = await self._db.set_menus(role_id, payload.menu_ids)
        if not role:
            raise RoleNotFoundError(role_id)
        await self._invalidate_role_users(role_id)
        return _to_out(role)

    async def delete(self, role_id: int) -> None:
        user_ids = await self._db.user_ids(role_id)
        if not await self._db.delete_role(role_id):
            raise RoleNotFoundError(role_id)
        for user_id in user_ids:
            self._auth.invalidate(user_id)

    async def _validate_menus(self, menu_ids: list[int]) -> None:
        missing = set(menu_ids) - await self._db.existing_menu_ids(menu_ids)
        if missing:
            raise MenuNotFoundError(min(missing))

    async def _invalidate_role_users(self, role_id: int) -> None:
        for user_id in await self._db.user_ids(role_id):
            self._auth.invalidate(user_id)

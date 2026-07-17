#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-17
# @description: Business logic for menu and button permission resources.

from __future__ import annotations

from typing import Any

from app.infra.db.database import Menu
from app.schemas.admin.permission import MenuCreate, MenuOut, MenuUpdate
from app.schemas.common import AlreadyExistsError, NotFoundError


class MenuNotFoundError(NotFoundError):
    def __init__(self, entity_id: Any):
        super().__init__("Menu", entity_id)


class MenuAlreadyExistsError(AlreadyExistsError):
    def __init__(self, entity_id: Any):
        super().__init__("Menu", entity_id)


def _to_out(menu: Menu, children: list[MenuOut] | None = None) -> MenuOut:
    return MenuOut(
        id=menu.id, parent_id=menu.parent_id, name=menu.name, title_key=menu.title_key,
        path=menu.path, component=menu.component, icon=menu.icon, sort_order=menu.sort_order,
        menu_type=menu.menu_type, description=menu.description, is_visible=menu.is_visible,
        is_active=menu.is_active, created_at=menu.created_at, children=children or [],
    )


class MenuService:
    def __init__(self, container) -> None:
        self._db = container.menu_db
        self._auth = container.auth

    async def list(self, tree: bool, menu_type: str | None, is_active: bool | None) -> list[MenuOut]:
        menus = await self._db.list_menus(menu_type, is_active)
        if not tree:
            return [_to_out(menu) for menu in menus]

        by_parent: dict[int | None, list[Menu]] = {}
        included = {menu.id for menu in menus}
        for menu in menus:
            parent_id = menu.parent_id if menu.parent_id in included else None
            by_parent.setdefault(parent_id, []).append(menu)

        def build(parent_id: int | None) -> list[MenuOut]:
            return [_to_out(menu, build(menu.id)) for menu in by_parent.get(parent_id, [])]

        return build(None)

    async def get(self, menu_id: int) -> MenuOut:
        menu = await self._db.get_by_id(menu_id)
        if not menu:
            raise MenuNotFoundError(menu_id)
        return _to_out(menu)

    async def create(self, payload: MenuCreate) -> MenuOut:
        await self._validate_parent(payload.parent_id)
        if await self._db.find_sibling(payload.parent_id, payload.name):
            raise MenuAlreadyExistsError(payload.name)
        return _to_out(await self._db.create_menu(payload.model_dump()))

    async def update(self, menu_id: int, payload: MenuUpdate) -> MenuOut:
        current = await self._db.get_by_id(menu_id)
        if not current:
            raise MenuNotFoundError(menu_id)
        data = payload.model_dump(exclude_unset=True)
        parent_id = data.get("parent_id", current.parent_id)
        if parent_id == menu_id or parent_id in await self._db.descendant_ids(menu_id):
            raise MenuAlreadyExistsError("cyclic parent")
        await self._validate_parent(parent_id)
        name = data.get("name", current.name)
        sibling = await self._db.find_sibling(parent_id, name)
        if sibling and sibling.id != menu_id:
            raise MenuAlreadyExistsError(name)
        affected = await self._db.affected_user_ids(menu_id)
        await self._db.update_fields(menu_id, data)
        for user_id in affected:
            self._auth.invalidate(user_id)
        return await self.get(menu_id)

    async def delete(self, menu_id: int) -> None:
        removed_ids = {menu_id} | await self._db.descendant_ids(menu_id)
        affected: set[int] = set()
        for removed_id in removed_ids:
            affected.update(await self._db.affected_user_ids(removed_id))
        if not await self._db.delete_menu(menu_id):
            raise MenuNotFoundError(menu_id)
        for user_id in affected:
            self._auth.invalidate(user_id)

    async def _validate_parent(self, parent_id: int | None) -> None:
        if parent_id is not None and not await self._db.get_by_id(parent_id):
            raise MenuNotFoundError(parent_id)

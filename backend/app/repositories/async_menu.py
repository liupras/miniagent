#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-23
# @description: User Database Management (Asynchronous)

from typing import  Dict, List
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.infra.db.async_base import AsyncBaseDatabase
from app.infra.db.database import Menu, Menu, Role, User
from app.core.constants import SUPER_PERMISSION
class AsyncMenuDatabase(AsyncBaseDatabase):

    async def get_by_id(self, menu_id: int) -> Menu | None:
        async with self.get_session() as session:
            return await session.get(Menu, menu_id)

    async def find_sibling(self, parent_id: int | None, name: str) -> Menu | None:
        async with self.get_session() as session:
            stmt = select(Menu).where(Menu.name == name)
            stmt = stmt.where(Menu.parent_id.is_(None)) if parent_id is None else stmt.where(Menu.parent_id == parent_id)
            return (await session.execute(stmt)).scalar_one_or_none()

    async def list_menus(
        self,
        menu_type: str | None = None,
        is_active: bool | None = None,
    ) -> list[Menu]:
        async with self.get_session() as session:
            stmt = select(Menu)
            if menu_type is not None:
                stmt = stmt.where(Menu.menu_type == menu_type)
            if is_active is not None:
                stmt = stmt.where(Menu.is_active == is_active)
            stmt = stmt.order_by(Menu.sort_order.asc(), Menu.id.asc())
            return list((await session.execute(stmt)).scalars().all())

    async def create_menu(self, data: dict) -> Menu:
        async with self.get_session() as session:
            menu = Menu(**data)
            session.add(menu)
            await session.flush()
            return menu

    async def update_fields(self, menu_id: int, data: dict) -> Menu | None:
        async with self.get_session() as session:
            menu = await session.get(Menu, menu_id)
            if not menu:
                return None
            for field, value in data.items():
                setattr(menu, field, value)
            await session.flush()
            return menu

    async def descendant_ids(self, menu_id: int) -> set[int]:
        menus = await self.list_menus()
        children: dict[int, list[int]] = {}
        for menu in menus:
            if menu.parent_id is not None:
                children.setdefault(menu.parent_id, []).append(menu.id)
        found: set[int] = set()
        pending = list(children.get(menu_id, []))
        while pending:
            child_id = pending.pop()
            if child_id not in found:
                found.add(child_id)
                pending.extend(children.get(child_id, []))
        return found

    async def delete_menu(self, menu_id: int) -> bool:
        async with self.get_session() as session:
            menu = await session.get(
                Menu,
                menu_id,
                options=[selectinload(Menu.children), selectinload(Menu.roles)],
            )
            if not menu:
                return False
            await session.delete(menu)
            return True

    async def affected_user_ids(self, menu_id: int) -> list[int]:
        """Users whose cached permissions may contain this menu code."""
        from app.infra.db.database import RoleMenuRelation, UserRoleRelation

        async with self.get_session() as session:
            stmt = (
                select(UserRoleRelation.user_id)
                .join(RoleMenuRelation, RoleMenuRelation.role_id == UserRoleRelation.role_id)
                .where(RoleMenuRelation.menu_id == menu_id)
                .distinct()
            )
            return list((await session.execute(stmt)).scalars())

    async def is_super_user(self,user_id: int) -> bool:
        async with self.get_session() as session:
            stmt = (
                select(Role.id)
                .select_from(User)
                .join(User.roles)
                .where(
                    User.id == user_id,
                    Role.is_super.is_(True)
                )
                .limit(1)
            )

            result = await session.execute(stmt)

            if result.scalar_one_or_none():
                return True
            
            return False
        
            
    async def get_user_resource_codes(self,user_id: int) -> set[str]:
        """Retrieve all menu/button names owned by this user at once."""
        is_super = await self.is_super_user(user_id=user_id)
        if is_super:
            return {SUPER_PERMISSION}
        else:
            async with self.get_session() as session:
                stmt = (
                    select(Menu.name)
                    .select_from(User)
                    .join(User.roles)
                    .join(Role.menus)
                    .where(User.id == user_id,Menu.is_active.is_(True))
                )
                result = await session.execute(stmt)

                return set(result.scalars().all())
        
    async def get_user_routes(self, username: str) -> tuple[List[str], Dict[int, Menu],set[str]]:
        """Query the menus and permissions bound to all user roles, and construct the pureAdmin route tree."""

        async with self.get_session() as session:
            stmt = (
                select(User)
                .where(User.username == username, User.is_active == True)
                .options(
                    selectinload(User.roles).selectinload(Role.menus),    
                )
            )
            result = await session.execute(stmt)
            user: User | None = result.scalar_one_or_none()

            if not user:
                return [], {}, set()

            is_super = any(r.is_super for r in user.roles)
            role_codes = [r.code for r in user.roles]

            if is_super:

                result = await session.execute(
                    select(Menu).where(
                        Menu.is_active.is_(True),
                        Menu.is_visible.is_(True)
                    )
                )

                menu_map = {
                    menu.id: menu
                    for menu in result.scalars().all()
                }

                return (
                    role_codes,
                    menu_map,
                    {SUPER_PERMISSION}
                )
            
            menu_map: Dict[int, Menu] = {}
            perm_codes: set[str] = set()

            for role in user.roles:
                for menu in role.menus:
                    if not menu.is_active:
                        continue
                    if not menu.is_visible:
                        continue

                    menu_map[menu.id] = menu
                    perm_codes.add(menu.name)   # The permissions include the name with menu_type="menu".

            return role_codes, menu_map, perm_codes

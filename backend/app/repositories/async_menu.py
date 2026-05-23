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

class AsyncMenuDatabase(AsyncBaseDatabase):
    async def get_user_routes(self, username: str) -> tuple[List[str], Dict[int, Menu],set[str]]:
        """Query the menus and permissions bound to all user roles, and construct the pureAdmin route tree."""

        async with self.get_session() as session:
            stmt = (
                select(User)
                .where(User.username == username, User.is_active == True)
                .options(
                    selectinload(User.roles).selectinload(Role.menus),
                    selectinload(User.roles).selectinload(Role.permissions),
                )
            )
            result = await session.execute(stmt)
            user: User | None = result.scalar_one_or_none()

            if not user:
                return [], {}, set()

            is_super = any(r.is_super for r in user.roles)
            role_codes = [r.code for r in user.roles]

            # ── Merge and deduplicate: Menus and permissions accessible to all roles. ────────────────────────────────
            if is_super:
                all_menus_result = await session.execute(
                    select(Menu).where(Menu.is_active == True, Menu.is_visible == True)
                )
                menu_map: dict[int, Menu] = {m.id: m for m in all_menus_result.scalars().all()}
                perm_codes: set[str] = {"*:*:*"}    # Super User: View the full menu, with permissions ["*:*:*"]
            else:
                menu_map: dict[int, Menu] = {}
                perm_codes: set[str] = set()
                for role in user.roles:
                    for menu in role.menus:
                        if menu.is_active and menu.is_visible:
                            menu_map[menu.id] = menu
                    for perm in role.permissions:
                        perm_codes.add(perm.code)

            return role_codes, menu_map, perm_codes
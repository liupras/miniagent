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

                    if menu.menu_type == "button":
                        perm_codes.add(menu.name)

            return role_codes, menu_map, perm_codes
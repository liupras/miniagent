#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description:  Asynchronous persistence operations for roles and role-menu bindings.

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.infra.db.async_base import AsyncBaseDatabase
from app.infra.db.database import Menu, Role, UserRoleRelation


class AsyncRoleDatabase(AsyncBaseDatabase):
    async def get_by_id(self, role_id: int) -> Role | None:
        async with self.get_session() as session:
            result = await session.execute(
                select(Role).options(selectinload(Role.menus)).where(Role.id == role_id)
            )
            return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Role | None:
        async with self.get_session() as session:
            return (await session.execute(select(Role).where(Role.code == code))).scalar_one_or_none()

    async def list_roles(
        self, page: int, page_size: int, keyword: str | None = None
    ) -> tuple[list[tuple[Role, int]], int]:
        async with self.get_session() as session:
            user_count = (
                select(func.count(UserRoleRelation.user_id))
                .where(UserRoleRelation.role_id == Role.id)
                .correlate(Role)
                .scalar_subquery()
            )
            stmt = select(Role, user_count.label("user_count")).options(selectinload(Role.menus))
            count_stmt = select(func.count()).select_from(Role)
            if keyword:
                like = f"%{keyword}%"
                condition = Role.code.ilike(like) | Role.name.ilike(like)
                stmt = stmt.where(condition)
                count_stmt = count_stmt.where(condition)
            total = (await session.execute(count_stmt)).scalar_one()
            rows = (
                await session.execute(
                    stmt.order_by(Role.is_super.desc(), Role.id.asc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
            return [(row[0], row[1]) for row in rows], total

    async def options(self) -> list[Role]:
        async with self.get_session() as session:
            return list((await session.execute(select(Role).order_by(Role.name))).scalars().all())

    async def create_role(self, data: dict, menu_ids: list[int]) -> Role:
        async with self.get_session() as session:
            menus = list((await session.execute(select(Menu).where(Menu.id.in_(set(menu_ids))))).scalars()) if menu_ids else []
            role = Role(**data, menus=menus)
            session.add(role)
            await session.flush()
            await session.refresh(role, attribute_names=["menus"])
            return role

    async def update_fields(self, role_id: int, data: dict) -> Role | None:
        async with self.get_session() as session:
            role = await session.get(Role, role_id)
            if not role:
                return None
            for field, value in data.items():
                setattr(role, field, value)
            await session.flush()
            return role

    async def set_menus(self, role_id: int, menu_ids: list[int]) -> Role | None:
        async with self.get_session() as session:
            role = (
                await session.execute(
                    select(Role).options(selectinload(Role.menus)).where(Role.id == role_id)
                )
            ).scalar_one_or_none()
            if not role:
                return None
            role.menus = list((await session.execute(select(Menu).where(Menu.id.in_(set(menu_ids))))).scalars()) if menu_ids else []
            await session.flush()
            await session.refresh(role, attribute_names=["menus"])
            return role

    async def delete_role(self, role_id: int) -> bool:
        async with self.get_session() as session:
            role = await session.get(Role, role_id, options=[selectinload(Role.users), selectinload(Role.menus)])
            if not role:
                return False
            await session.delete(role)
            return True

    async def user_ids(self, role_id: int) -> list[int]:
        async with self.get_session() as session:
            return list((await session.execute(select(UserRoleRelation.user_id).where(UserRoleRelation.role_id == role_id))).scalars())

    async def existing_menu_ids(self, menu_ids: list[int]) -> set[int]:
        if not menu_ids:
            return set()
        async with self.get_session() as session:
            return set((await session.execute(select(Menu.id).where(Menu.id.in_(set(menu_ids))))).scalars())

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-30
# @description: User Service – business logic layer

from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.infra.db.database import Role, User
from app.repositories.async_user import AsyncUserDatabase
from app.repositories.async_menu import AsyncMenuDatabase
from app.schemas.common import PageResult
from app.schemas.admin.user import UserListParams, UserOptionItem, UserOut
from app.core.constants import SUPER_PERMISSION


# ──────────────────────────────────────────────
# Domain exceptions
# ──────────────────────────────────────────────

class UserNotFoundError(Exception):
    def __init__(self, username: str):
        self.username = username
        super().__init__(f"User '{username}' not found")


# ──────────────────────────────────────────────
# Permission helper (mirrors async_user.py logic)
# ──────────────────────────────────────────────

def _calc_permissions(user: User) -> List[str]:
    """Derive the flat permission list from a User's loaded roles."""
    if any(role.is_super for role in user.roles):
        return [SUPER_PERMISSION]
    perms: set[str] = {p.code for role in user.roles for p in role.permissions}
    return list(perms)


def _to_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        nickname=user.nickname,
        avatar=user.avatar,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login=user.last_login,
        roles=[r.code for r in user.roles] if user.roles else ["common"],
        permissions=_calc_permissions(user),
    )


# ──────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────

class UserService:
    """
    Business logic for the User resource.

    Delegates low-level DB operations (auth, password, deactivate …) to
    AsyncUserDatabase and owns the queries that need pagination / extra joins.
    """

    def __init__(self, user_db: AsyncUserDatabase, menu_db: AsyncMenuDatabase) -> None:
        self._user_db = user_db
        self._menu_db = menu_db

    # ── Options endpoint ──────────────────────────────────────────────────

    async def get_options(
        self,
        is_active: Optional[bool] = True,
    ) -> List[UserOptionItem]:
        """
        Return lightweight id + username + nickname tuples for every user,
        ordered by username.  Used by frontend dropdown selectors.

        By default only active users are returned (is_active=True).
        Pass is_active=None to return all users regardless of status.
        """
        async with self._user_db.get_session() as session:
            stmt = select(User).order_by(User.username)
            if is_active is not None:
                stmt = stmt.where(User.is_active == is_active)
            rows: List[User] = list((await session.execute(stmt)).scalars().all())

        return [UserOptionItem.model_validate(r) for r in rows]

    # ── Paginated list ────────────────────────────────────────────────────

    async def list_users(self, params: UserListParams) -> PageResult[UserOut]:
        """Paginated + filtered user list with roles and permissions."""
        async with self._user_db.get_session() as session:
            stmt = select(User).options(
                selectinload(User.roles).selectinload(Role.permissions)
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

        return PageResult[UserOut](
            total=total,
            page=params.page,
            page_size=params.page_size,
            data=[_to_user_out(r) for r in rows],
        )

    # ── Single user ───────────────────────────────────────────────────────

    async def get_user(self, username: str) -> UserOut:
        """Return full user info or raise UserNotFoundError."""
        info = await self._user_db.get_user_info(username)        
        if info is None:
            raise UserNotFoundError(username)
        permissions = await self._menu_db.get_user_resource_codes(info["id"])
        info["permissions"] = list(permissions)
        return info
    
    async def verify_user(self, username: str, password: str) -> bool:
        """Verify username/password for login."""
        return await self._user_db.verify_user(username, password)
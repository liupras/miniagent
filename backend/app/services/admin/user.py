#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-30
# @description: User Service – business logic layer

from typing import Any, List, Optional

from app.infra.db.database import User
from app.repositories.async_user import AsyncUserDatabase
from app.repositories.async_menu import AsyncMenuDatabase
from app.schemas.common import NotFoundError, PageResult,AlreadyExistsError
from app.schemas.admin.user import UserListParams, UserOptionItem, UserOut


class UserNotFoundError(NotFoundError):
    def __init__(self, entity_id: Any):
        super().__init__("User", entity_id)

def _to_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        nickname=user.nickname,
        avatar=user.avatar,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login=user.last_login,
        roles=[r.code for r in user.roles] if user.roles else ["common"]       
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
        users = await self._user_db.get_options(is_active)

        return [
            UserOptionItem.model_validate(u)
            for u in users
        ]

    # ── Paginated list ────────────────────────────────────────────────────

    async def list_users(self, params: UserListParams) -> PageResult[UserOut]:
        """Paginated + filtered user list with roles."""

        rows, total = await self._user_db.list_users(params)

        return PageResult(
            total=total,
            page=params.page,
            page_size=params.page_size,
            data=[_to_user_out(r) for r in rows]
        )

    # ── Single user ───────────────────────────────────────────────────────

    async def get_user(self, username: str) -> UserOut:
        """Return full user info or raise UserNotFoundError."""
        info = await self._user_db.get_user_info(username)        
        if info is None:
            raise UserNotFoundError(username)
        permissions = await self._menu_db.get_user_resource_codes(info["id"])
        info["permissions"] = list(permissions)
        return UserOut.model_validate(info)
    
    async def verify_user(self, username: str, password: str) -> bool:
        """Verify username/password for login."""
        return await self._user_db.verify_user(username, password)
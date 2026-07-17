"""Integration coverage for the user/role/menu asynchronous repositories."""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infra.db.database import Base
from app.repositories.async_menu import AsyncMenuDatabase
from app.repositories.async_role import AsyncRoleDatabase
from app.repositories.async_user import AsyncUserDatabase
from app.schemas.admin.user import UserListParams


def test_user_role_menu_crud_and_bindings():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        menu_db = AsyncMenuDatabase(engine, sessions)
        role_db = AsyncRoleDatabase(engine, sessions)
        user_db = AsyncUserDatabase(engine, sessions)

        root = await menu_db.create_menu({"name": "system:default", "title_key": "system"})
        button = await menu_db.create_menu({
            "parent_id": root.id,
            "name": "user:list",
            "title_key": "users",
            "menu_type": "button",
        })
        await menu_db.create_menu({
            "parent_id": button.id,
            "name": "user:list:export",
            "title_key": "export",
            "menu_type": "button",
        })
        role = await role_db.create_role(
            {"code": "operator", "name": "Operator", "is_super": False},
            [root.id, button.id],
        )
        user = await user_db.create_user(
            "operator1", "secret123", nickname="Operator", role_ids=[role.id]
        )

        assert user is not None
        assert [item.code for item in user.roles] == ["operator"]
        rows, total = await user_db.list_users(
            UserListParams(page=1, page_size=20, keyword="Oper", role_id=role.id)
        )
        assert total == 1
        assert rows[0].username == "operator1"
        assert await menu_db.get_user_resource_codes(user.id) == {"system:default", "user:list"}

        await role_db.set_menus(role.id, [root.id])
        assert await menu_db.get_user_resource_codes(user.id) == {"system:default"}
        await user_db.set_roles(user.id, [])
        assert await menu_db.get_user_resource_codes(user.id) == set()

        assert await user_db.delete_user(user.id)
        assigned_user = await user_db.create_user(
            "operator2", "secret123", role_ids=[role.id]
        )
        assert assigned_user is not None
        assert await user_db.delete_user(assigned_user.id)
        assert await role_db.delete_role(role.id)
        assert await menu_db.delete_menu(root.id)
        await engine.dispose()

    asyncio.run(scenario())

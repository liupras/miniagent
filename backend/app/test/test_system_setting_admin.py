import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infra.db.database import SystemSetting
from app.repositories.async_system_setting import AsyncSystemSettingDatabase
from app.schemas.admin.system_setting import SystemSettingUpdate
from app.services.admin.system_setting import (
    SystemSettingNotFoundError,
    SystemSettingReadOnlyError,
    SystemSettingService,
    SystemSettingValueError,
)


def test_system_setting_view_edit_and_validation():
    asyncio.run(_exercise_system_settings())


async def _exercise_system_settings():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(SystemSetting.__table__.create)

    async with session_factory() as session:
        session.add_all(
            [
                SystemSetting(key="name", value="MiniAgent", group="general"),
                SystemSetting(
                    key="enabled", value="false", value_type="bool", group="general"
                ),
                SystemSetting(
                    key="options", value="{}", value_type="json", group="advanced"
                ),
                SystemSetting(key="version", value="1.0", is_readonly=True),
            ]
        )
        await session.commit()

    service = SystemSettingService(
        AsyncSystemSettingDatabase(engine, session_factory)
    )
    assert len(await service.list_settings()) == 4
    assert len(await service.list_settings("general")) == 2

    updated = await service.update_setting(
        "enabled", SystemSettingUpdate(value=" TRUE ")
    )
    assert updated.value == "true"

    await service.update_setting(
        "options", SystemSettingUpdate(value='{"limit": 10}')
    )
    with pytest.raises(SystemSettingValueError):
        await service.update_setting("options", SystemSettingUpdate(value="{"))
    with pytest.raises(SystemSettingReadOnlyError):
        await service.update_setting("version", SystemSettingUpdate(value="2.0"))
    with pytest.raises(SystemSettingNotFoundError):
        await service.get_setting("missing")

    await engine.dispose()

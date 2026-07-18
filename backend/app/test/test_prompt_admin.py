import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infra.db.database import Prompt
from app.repositories.async_prompt import AsyncPromptDatabase
from app.schemas.admin.prompt import PromptCreate, PromptUpdate
from app.services.admin.prompt import (
    PromptAlreadyExistsError,
    PromptNotFoundError,
    PromptService,
)


def test_prompt_crud_and_language_normalization():
    asyncio.run(_exercise_prompt_crud())


async def _exercise_prompt_crud():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Prompt.__table__.create)

    service = PromptService(AsyncPromptDatabase(engine, session_factory))
    created = await service.create(
        PromptCreate(
            key=" demo.prompt ",
            lang="zh-cn",
            value="Hello {name}",
            description="demo",
        )
    )
    assert created.key == "demo.prompt"
    assert created.lang == "zh_CN"

    with pytest.raises(PromptAlreadyExistsError):
        await service.create(
            PromptCreate(key="demo.prompt", lang="ZH_cn", value="duplicate")
        )

    page = await service.list_prompts(keyword="demo", lang="zh_CN")
    assert page.total == 1
    assert page.data[0].value == "Hello {name}"

    updated = await service.update(
        "demo.prompt",
        "zh_cn",
        PromptUpdate(value="Updated", description=None),
    )
    assert updated.value == "Updated"
    assert updated.description is None
    assert await service.list_languages() == ["zh_CN"]

    await service.delete("demo.prompt", "ZH-CN")
    with pytest.raises(PromptNotFoundError):
        await service.get_prompt("demo.prompt", "zh_CN")

    await engine.dispose()

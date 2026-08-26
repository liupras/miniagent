import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.language import normalize_language
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


def test_legacy_regional_language_rows_remain_accessible():
    asyncio.run(_exercise_legacy_regional_language_row())


@pytest.mark.parametrize(
    ("language_tag", "expected"),
    [
        ("zh", "zh"),
        ("ZH", "zh"),
        ("zh-CN", "zh"),
        ("zh_CN", "zh"),
        ("en", "en"),
        ("EN", "en"),
        ("en-US", "en"),
        ("en_GB", "en"),
    ],
)
def test_supported_language_variants_collapse_to_base_language(
    language_tag,
    expected,
):
    assert normalize_language(language_tag) == expected


@pytest.mark.parametrize("language_tag", ["fr", "de-DE", "", "  "])
def test_unsupported_prompt_languages_are_rejected(language_tag):
    with pytest.raises(ValueError, match="only supports Chinese"):
        normalize_language(language_tag)


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
    assert created.lang == "zh"

    with pytest.raises(PromptAlreadyExistsError):
        await service.create(
            PromptCreate(key="demo.prompt", lang="ZH", value="duplicate")
        )

    page = await service.list_prompts(keyword="demo", lang="zh")
    assert page.total == 1
    assert page.data[0].value == "Hello {name}"

    updated = await service.update(
        "demo.prompt",
        "zh",
        PromptUpdate(value="Updated", description=None),
    )
    assert updated.value == "Updated"
    assert updated.description is None
    assert await service.list_languages() == ["zh"]

    await service.delete("demo.prompt", "ZH-CN")
    with pytest.raises(PromptNotFoundError):
        await service.get_prompt("demo.prompt", "zh")

    await engine.dispose()


async def _exercise_legacy_regional_language_row():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Prompt.__table__.create)

    async with session_factory() as session:
        session.add(Prompt(key="legacy.prompt", lang="zh_CN", value="旧数据"))
        await session.commit()

    database = AsyncPromptDatabase(engine, session_factory)
    assert await database.get_value("legacy.prompt", "zh-CN") == "旧数据"

    updated = await database.upsert("legacy.prompt", "ZH", "新数据")
    assert updated.lang == "zh"
    assert updated.value == "新数据"

    await engine.dispose()

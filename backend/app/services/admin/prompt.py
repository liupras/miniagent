#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-27
# @description: Prompt

from typing import Dict, Optional

from app.repositories.async_prompt import AsyncPromptDatabase, normalize_prompt_lang
from app.schemas.admin.prompt import (
    PromptBulkUpsert,
    PromptBulkResult,
    PromptCreate,
    PromptOut,
    PromptUpdate,
)
from app.schemas.common import AlreadyExistsError, NotFoundError, PageResult


class PromptNotFoundError(NotFoundError):
    def __init__(self, key: str, lang: str) -> None:
        super().__init__("Prompt", f"{key}@{lang}")


class PromptAlreadyExistsError(AlreadyExistsError):
    def __init__(self, key: str, lang: str) -> None:
        super().__init__("Prompt", f"{key}@{lang}")

class PromptService:

    def __init__(self, db: AsyncPromptDatabase) -> None:
        self._db = db

    async def list_prompts(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        lang: Optional[str] = None,
    ) -> PageResult[PromptOut]:
        rows = await self._db.get_all()
        if keyword:
            needle = keyword.strip().lower()
            rows = [
                row
                for row in rows
                if needle in row.key.lower()
                or needle in (row.description or "").lower()
            ]
        if lang:
            normalized = lang.strip().replace("-", "_").lower()
            rows = [row for row in rows if row.lang.lower() == normalized]

        total = len(rows)
        start = (page - 1) * page_size
        return PageResult(
            total=total,
            page=page,
            page_size=page_size,
            data=[PromptOut.model_validate(row) for row in rows[start:start + page_size]],
        )

    async def list_languages(self) -> list[str]:
        languages = await self._db.list_supported_languages()
        return sorted({normalize_prompt_lang(lang) for lang in languages})

    async def get_prompt(self, key: str, lang: str) -> PromptOut:
        row = await self._db.get(key, lang)
        if row is None:
            raise PromptNotFoundError(key, lang)
        return PromptOut.model_validate(row)

    async def create(self, payload: PromptCreate) -> PromptOut:
        if await self._db.get(payload.key, payload.lang):
            raise PromptAlreadyExistsError(payload.key, payload.lang)
        row = await self._db.upsert(**payload.model_dump())
        await self._reload_prompt_loader()
        return PromptOut.model_validate(row)

    async def update(
        self,
        key: str,
        lang: str,
        payload: PromptUpdate,
    ) -> PromptOut:
        if await self._db.get(key, lang) is None:
            raise PromptNotFoundError(key, lang)
        # upsert_many can explicitly clear a nullable description, while the
        # single-row repository upsert intentionally treats None as unchanged.
        await self._db.upsert_many(
            [{"key": key, "lang": lang, **payload.model_dump()}]
        )
        await self._reload_prompt_loader()
        return await self.get_prompt(key, lang)

    async def bulk_upsert(self, payload: PromptBulkUpsert) -> PromptBulkResult:
        created, updated = await self._db.upsert_many(
            [item.model_dump() for item in payload.items]
        )
        await self._reload_prompt_loader()
        return PromptBulkResult(created=created, updated=updated)

    async def delete(self, key: str, lang: str) -> None:
        if not await self._db.delete(key, lang):
            raise PromptNotFoundError(key, lang)
        await self._reload_prompt_loader()

    async def _reload_prompt_loader(self) -> None:
        # Imported lazily to avoid the service/loader module cycle at startup.
        from app.core import prompt_loader as loader_module

        if loader_module.prompt_loader is not None:
            await loader_module.prompt_loader.initialize()

    async def get_all_as_dict(self) -> Dict[str, Dict[str, str]]:

        prompts = await self._db.get_all()
        prompt_dict: Dict[str, Dict[str, str]] = {}
        for p in prompts:
            if p.key not in prompt_dict:
                prompt_dict[p.key] = {}
            prompt_dict[p.key][normalize_prompt_lang(p.lang)] = p.value

        return prompt_dict

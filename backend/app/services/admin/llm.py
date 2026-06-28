#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-30
# @description: LLM Service – business logic layer

from typing import Any, List, Optional

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from loguru import logger

from app.infra.db.database import LLM
from app.repositories.async_llm import AsyncLLMDatabase
from app.schemas.admin.llm import (
    LLMCreate,
    LLMUpdate,
    LLMUpsert,
    LLMOut,
    LLMOptionItem,
    LLMListParams,
)
from app.schemas.common import NotFoundError, AlreadyExistsError,PageResult

class LLMNotFoundError(NotFoundError):
    def __init__(self, entity_id: Any):
        super().__init__("LLM", entity_id)

class LLMAlreadyExistsError(AlreadyExistsError):
    def __init__(self, entity_id: Any):
        super().__init__("LLM", entity_id)


# ──────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────

class LLMService:
    """
    All business logic for the LLM resource.

    Delegates raw DB access to AsyncLLMDatabase and owns the queries that
    require pagination or extra filtering beyond what the DB layer exposes.
    Raises domain exceptions; the router maps them to HTTP responses.
    """

    def __init__(self, db: AsyncLLMDatabase) -> None:
        self._db = db

    # ── Read ──────────────────────────────────────────────────────────────

    async def get_llm(self, llm_id: int) -> LLM:
        """Return an LLM ORM object or raise LLMNotFoundError."""
        row = await self._db.get(llm_id)
        if row is None:
            raise LLMNotFoundError(llm_id)
        return row

    async def list_llms(self, params: LLMListParams) -> PageResult:
        """Paginated + filtered LLM list."""
        async with self._db.get_session() as session:
            stmt = select(LLM)

            if params.provider_name:
                stmt = stmt.where(LLM.provider_name == params.provider_name)
            if params.model_name:
                stmt = stmt.where(LLM.model_name.ilike(f"%{params.model_name}%"))

            total: int = (
                await session.execute(
                    select(func.count()).select_from(stmt.subquery())
                )
            ).scalar_one()

            offset = (params.page - 1) * params.page_size
            stmt = (
                stmt.order_by(LLM.provider_name, LLM.model_name)
                .offset(offset)
                .limit(params.page_size)
            )
            rows: List[LLM] = list((await session.execute(stmt)).scalars().all())

        return PageResult(
            total=total,
            page=params.page,
            page_size=params.page_size,
            data=[LLMOut.model_validate(r) for r in rows],
        )

    async def get_options(
        self, provider_name: Optional[str] = None
    ) -> List[LLMOptionItem]:
        """
        Return lightweight id + name + provider_name + model_name tuples,
        used by frontend dropdown selectors (e.g. the Agent form).

        Optionally filtered by provider_name.
        """
        if provider_name:
            rows = await self._db.get_all_by_provider(provider_name)
        else:
            rows = await self._db.get_all()

        return [LLMOptionItem.model_validate(r) for r in rows]

    async def list_providers(self) -> List[str]:
        return await self._db.list_providers()

    async def list_models(self, provider_name: Optional[str] = None) -> List[str]:
        return await self._db.list_models(provider_name)

    # ── Create ────────────────────────────────────────────────────────────

    async def create_llm(self, payload: LLMCreate) -> LLMOut:
        """Create a new LLM. Raises LLMConflictError on duplicate."""
        try:
            row = await self._db.create(
                provider_name=payload.provider_name,
                base_url=payload.base_url,
                model_name=payload.model_name,
                api_key=payload.api_key,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
                capabilities=payload.capabilities,
            )
        except IntegrityError as exc:
            logger.error(exec)
            raise LLMAlreadyExistsError(f"LLM '{payload.provider_name}/{payload.model_name}'")
  

        # patch the name field (not handled by AsyncLLMDatabase.create)
        updated = await self._db.update(row.id, name=payload.name)
        return LLMOut.model_validate(updated or row)

    # ── Upsert ────────────────────────────────────────────────────────────

    async def upsert_llm(self, payload: LLMUpsert) -> LLMOut:
        """Insert or update by (provider_name, model_name)."""
        row = await self._db.upsert(
            provider_name=payload.provider_name,
            base_url=payload.base_url,
            model_name=payload.model_name,
            api_key=payload.api_key,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            capabilities=payload.capabilities,
        )
        updated = await self._db.update(row.id, name=payload.name)
        return LLMOut.model_validate(updated or row)

    # ── Update ────────────────────────────────────────────────────────────

    async def update_llm(self, llm_id: int, payload: LLMUpdate) -> LLMOut:
        """Partial update. Raises LLMNotFoundError / LLMConflictError."""
        fields = payload.model_dump(exclude_unset=True)
        if not fields:
            row = await self.get_llm(llm_id)   # validates existence
            return LLMOut.model_validate(row)

        try:
            row = await self._db.update(llm_id, **fields)
        except IntegrityError as exc:
            logger.error(exc)
            raise LLMAlreadyExistsError(f"LLM '{payload.provider_name}/{payload.model_name}'")

        if row is None:
            raise LLMNotFoundError(llm_id)

        return LLMOut.model_validate(row)

    # ── Delete ────────────────────────────────────────────────────────────

    async def delete_llm(self, llm_id: int) -> None:
        """Delete by primary key. Raises LLMNotFoundError if missing."""
        deleted = await self._db.delete(llm_id)
        if not deleted:
            raise LLMNotFoundError(llm_id)
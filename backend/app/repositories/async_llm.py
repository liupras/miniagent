#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-27
# @description: LLM Database Management (Asynchronous Version)

from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select

from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import LLM


class AsyncLLMDatabase(AsyncBaseDatabase):
    """
    CRUD operations for the LLM table - Asynchronous Version.
    """

    # ── Read ──────────────────────────────────────────────────────────────

    async def get(self, llm_id: int) -> Optional[LLM]:
        """
        Return the LLM row for *llm_id*, or None.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(LLM).where(LLM.id == llm_id)
            )
            row = result.scalar_one_or_none()

        if row is None:
            logger.debug(f"[DB] LLM not found: id={llm_id}")
        else:
            logger.debug(f"[DB] LLM get: id={llm_id} ({row!r})")
        return row

    async def get_by_provider_model(
        self, provider_name: str, model_name: str
    ) -> Optional[LLM]:
        """
        Return the LLM row matching the unique *(provider_name, model_name)*
        constraint, or None.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(LLM).where(
                    LLM.provider_name == provider_name,
                    LLM.model_name    == model_name,
                )
            )
            row = result.scalar_one_or_none()

        if row is None:
            logger.debug(
                f"[DB] LLM not found: provider='{provider_name}' model='{model_name}'"
            )
        else:
            logger.debug(
                f"[DB] LLM get_by_provider_model: "
                f"provider='{provider_name}' model='{model_name}'"
            )
        return row

    async def get_all(self) -> List[LLM]:
        """
        Return every LLM row ordered by provider_name, model_name.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(LLM).order_by(LLM.provider_name, LLM.model_name)
            )
            rows = result.scalars().all()

        logger.debug(f"[DB] LLM get_all: found={len(rows)}")
        return list(rows)

    async def get_all_by_provider(self, provider_name: str) -> List[LLM]:
        """
        Return all LLM rows for *provider_name*, ordered by model_name.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(LLM)
                .where(LLM.provider_name == provider_name)
                .order_by(LLM.model_name)
            )
            rows = result.scalars().all()

        logger.debug(
            f"[DB] LLM get_all_by_provider: "
            f"provider='{provider_name}' found={len(rows)}"
        )
        return list(rows)

    async def list_providers(self) -> List[str]:
        """
        Return a sorted list of all distinct provider names in the table.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(LLM.provider_name).distinct().order_by(LLM.provider_name)
            )
            providers = result.scalars().all()

        logger.debug(f"[DB] LLM providers: {providers}")
        return list(providers)

    async def list_models(self, provider_name: Optional[str] = None) -> List[str]:
        """
        Return a sorted list of all distinct model names.
        Optionally filtered by *provider_name*.
        """
        async with self.get_session() as session:
            stmt = select(LLM.model_name).distinct()
            if provider_name is not None:
                stmt = stmt.where(LLM.provider_name == provider_name)
            result = await session.execute(stmt.order_by(LLM.model_name))
            models = result.scalars().all()

        logger.debug(
            f"[DB] LLM list_models (provider={provider_name!r}): {models}"
        )
        return list(models)

    # ── Write ─────────────────────────────────────────────────────────────

    async def create(
        self,
        provider_name: str,
        base_url:      str,
        model_name:    str,
        api_key:       Optional[str]  = None,
        temperature:   float          = 0.7,
        max_tokens:    int            = 2000,
        capabilities:  Optional[Dict] = None,
    ) -> LLM:
        """
        Insert a new LLM row and return it.

        Raises ``sqlalchemy.exc.IntegrityError`` if the
        *(provider_name, model_name)* pair already exists.
        """
        async with self.get_session() as session:
            row = LLM(
                provider_name = provider_name,
                base_url      = base_url,
                model_name    = model_name,
                api_key       = api_key,
                temperature   = temperature,
                max_tokens    = max_tokens,
                capabilities  = capabilities,
            )
            session.add(row)
            await session.flush()   # populate row.id before context exits
            await session.refresh(row)

        logger.info(
            f"[DB] LLM created: id={row.id} "
            f"provider='{provider_name}' model='{model_name}'"
        )
        return row

    async def upsert(
        self,
        provider_name: str,
        base_url:      str,
        model_name:    str,
        api_key:       Optional[str]  = None,
        temperature:   float          = 0.7,
        max_tokens:    int            = 2000,
        capabilities:  Optional[Dict] = None,
    ) -> LLM:
        """
        Insert or update the row for *(provider_name, model_name)*.

        - If the row does not exist it is created.
        - If it already exists, every supplied field is updated.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(LLM).where(
                    LLM.provider_name == provider_name,
                    LLM.model_name    == model_name,
                )
            )
            row = result.scalar_one_or_none()

            if row is None:
                row = LLM(
                    provider_name = provider_name,
                    base_url      = base_url,
                    model_name    = model_name,
                    api_key       = api_key,
                    temperature   = temperature,
                    max_tokens    = max_tokens,
                    capabilities  = capabilities,
                )
                session.add(row)
                logger.info(
                    f"[DB] LLM created: provider='{provider_name}' model='{model_name}'"
                )
            else:
                row.base_url     = base_url
                row.api_key      = api_key
                row.temperature  = temperature
                row.max_tokens   = max_tokens
                if capabilities is not None:
                    row.capabilities = capabilities
                logger.info(
                    f"[DB] LLM updated: id={row.id} "
                    f"provider='{provider_name}' model='{model_name}'"
                )

            await session.flush()
            await session.refresh(row)

        return row

    async def update(self, llm_id: int, **fields: Any) -> Optional[LLM]:
        """
        Partially update an existing LLM row by *llm_id*.

        Only the keys present in *fields* are modified.
        Allowed keys: ``base_url``, ``api_key``, ``temperature``,
        ``max_tokens``, ``capabilities``, ``provider_name``, ``model_name``.

        Returns the updated row, or None if not found.
        """
        allowed = {
            "base_url", "api_key", "temperature",
            "max_tokens", "capabilities", "provider_name", "model_name",
        }
        invalid = set(fields) - allowed
        if invalid:
            raise ValueError(f"Invalid field(s) for LLM.update: {invalid}")

        async with self.get_session() as session:
            result = await session.execute(
                select(LLM).where(LLM.id == llm_id)
            )
            row = result.scalar_one_or_none()

            if row is None:
                logger.warning(f"[DB] LLM.update: not found id={llm_id}")
                return None

            for field, value in fields.items():
                setattr(row, field, value)

            await session.flush()
            await session.refresh(row)

        logger.info(f"[DB] LLM updated: id={llm_id} fields={list(fields)}")
        return row

    async def delete(self, llm_id: int) -> bool:
        """
        Delete the LLM row for *llm_id*.

        Returns True if a row was deleted, False if it did not exist.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(LLM).where(LLM.id == llm_id)
            )
            row = result.scalar_one_or_none()

            if row is None:
                logger.warning(f"[DB] LLM.delete: not found id={llm_id}")
                return False

            await session.delete(row)

        logger.info(f"[DB] LLM deleted: id={llm_id}")
        return True

    async def delete_by_provider_model(
        self, provider_name: str, model_name: str
    ) -> bool:
        """
        Delete the LLM row identified by *(provider_name, model_name)*.

        Returns True if a row was deleted, False if it did not exist.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(LLM).where(
                    LLM.provider_name == provider_name,
                    LLM.model_name    == model_name,
                )
            )
            row = result.scalar_one_or_none()

            if row is None:
                logger.warning(
                    f"[DB] LLM.delete_by_provider_model: not found "
                    f"provider='{provider_name}' model='{model_name}'"
                )
                return False

            await session.delete(row)

        logger.info(
            f"[DB] LLM deleted: provider='{provider_name}' model='{model_name}'"
        )
        return True

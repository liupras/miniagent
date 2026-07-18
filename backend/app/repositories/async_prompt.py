#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: Prompt Database Management (Asynchronous Version)

from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import func, select

from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import Prompt


def normalize_prompt_lang(lang: str) -> str:
    """Normalize language tags to the project's ``zh_CN`` / ``en_US`` form."""
    parts = lang.strip().replace("-", "_").split("_", 1)
    if len(parts) == 1:
        return parts[0].lower()
    return f"{parts[0].lower()}_{parts[1].upper()}"


class AsyncPromptDatabase(AsyncBaseDatabase):
    """
    CRUD operations for the Prompt table - Asynchronous Version.
    """

    # ── Read ──────────────────────────────────────────────────────────────

    async def get(self, key: str, lang: str) -> Optional[Prompt]:
        """
        Return the Prompt row for *(key, lang)*, or None.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(Prompt).where(         
                    Prompt.key   == key,
                    func.lower(Prompt.lang) == normalize_prompt_lang(lang).lower(),
                )
            )
            row = result.scalar_one_or_none()

        if row is None:
            logger.debug(
                f"[DB] Prompt not found: key='{key}' lang='{lang}'"
            )
        else:
            logger.debug(
                f"[DB] Prompt get: key='{key}' lang='{lang}'"
            )
        return row

    async def get_value(self, key: str, lang: str) -> Optional[str]:
        """
        Return just the translated string for *(key, lang)*, or None.
        """
        row = await self.get(key, lang)
        return row.value if row is not None else None

    async def get_all_by_lang(self, lang: str) -> List[Prompt]:
        """
        Return all rows for *(lang)*, ordered by key asynchronously.        
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(Prompt)
                .where(  
                    func.lower(Prompt.lang) == normalize_prompt_lang(lang).lower(),
                )
                .order_by(Prompt.key)
            )
            rows = result.scalars().all()

        logger.debug(
            f"[DB] Prompt get_all_by_lang: "
            f"lang='{lang}' found={len(rows)}"
        )
        return list(rows)

    async def get_all_by_key(self, key: str) -> List[Prompt]:
        """
        Return all language variants for *(key)*, ordered by lang.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(Prompt)
                .where(Prompt.key == key)
                .order_by(Prompt.lang)
            )
            rows = result.scalars().all()

        logger.debug(
            f"[DB] Prompt get_all_by_key: key='{key}' found={len(rows)}"
        )
        return list(rows)

    async def get_all(self) -> List[Prompt]:
        """
        Return every row ordered by key, lang asynchronously.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(Prompt).order_by(Prompt.key, Prompt.lang)
            )
            rows = result.scalars().all()

        logger.debug(f"[DB] Prompt get_all: found={len(rows)}")
        return list(rows)

    async def list_supported_languages(self, ) -> List[str]:
        """
        Return a sorted list of all language tags present in the table.
        """
        async with self.get_session() as session:
            stmt = select(Prompt.lang).distinct()   
            result = await session.execute(stmt.order_by(Prompt.lang))
            langs = result.scalars().all()

        logger.debug(f"[DB] Prompt supported languages: {langs}")
        return list(langs)

    # ── Write ─────────────────────────────────────────────────────────────

    async def upsert(
        self,        
        key:         str,
        lang:        str,
        value:       str,
        description: Optional[str] = None,
    ) -> Prompt:
        """
        Insert or update the row for *(key, lang)* asynchronously.
        """
        lang = normalize_prompt_lang(lang)

        async with self.get_session() as session:
            result = await session.execute(
                select(Prompt).where(                    
                    Prompt.key   == key,
                    func.lower(Prompt.lang) == lang.lower(),
                )
            )
            row = result.scalar_one_or_none()

            if row is None:
                row = Prompt(                   
                    key         = key,
                    lang        = lang,
                    value       = value,
                    description = description,
                )
                session.add(row)
                logger.info(f"[DB] Prompt created: [{lang}] /{key}")
            else:
                row.value = value
                if description is not None:
                    row.description = description
                logger.info(f"[DB] Prompt updated: [{lang}] /{key}")
            
            # The context manager will automatically commit.

        return row

    async def upsert_many(self, rows: List[Dict]) -> Tuple[int, int]:
        """
        Bulk upsert multiple Prompt rows asynchronously.
        """
        created = updated = 0

        async with self.get_session() as session:
            for item in rows:
                lang = normalize_prompt_lang(item["lang"])
                result = await session.execute(
                    select(Prompt).where(   
                        Prompt.key   == item["key"],
                        func.lower(Prompt.lang) == lang.lower(),
                    )
                )
                existing = result.scalar_one_or_none()

                if existing is None:
                    session.add(Prompt(
                        key         = item["key"],
                        lang        = lang,
                        value       = item["value"],
                        description = item.get("description"),
                    ))
                    created += 1
                else:
                    existing.value = item["value"]
                    if "description" in item:
                        existing.description = item["description"]
                    updated += 1

        logger.info(
            f"[DB] Prompt upsert_many: created={created} updated={updated}"
        )
        return created, updated

    async def delete(self, key: str, lang: str) -> bool:
        """
        Delete the row for *(key, lang)* asynchronously.
        """
        lang = normalize_prompt_lang(lang)

        async with self.get_session() as session:
            result = await session.execute(
                select(Prompt).where(    
                    Prompt.key   == key,
                    func.lower(Prompt.lang) == lang.lower(),
                )
            )
            row = result.scalar_one_or_none()

            if row is None:
                logger.warning(
                    f"[DB] Prompt.delete: not found [{lang}] /{key}"
                )
                return False

            await session.delete(row)

        logger.info(f"[DB] Prompt deleted: [{lang}] /{key}")
        return True

    async def delete_all_for_lang(self, lang: str) -> int:
        """
        Delete every row for *lang* asynchronously.
        """
        lang = normalize_prompt_lang(lang)

        async with self.get_session() as session:
            stmt = select(Prompt).where(func.lower(Prompt.lang) == lang.lower())
            result = await session.execute(stmt)
            rows = result.scalars().all()

            if not rows:
                logger.warning(
                    f"[DB] Prompt.delete_all_for_lang: no rows for "
                    f"lang='{lang}'"
                )
                return 0

            count = len(rows)
            for row in rows:
                await session.delete(row)

        logger.info(
            f"[DB] Prompt deleted all for lang='{lang}': "
            f"count={count}"
        )
        return count

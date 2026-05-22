#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: I18n Database Management (Asynchronous Version)

from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import select

from ..infra.db.async_base import AsyncBaseDatabase
from ..infra.db.database import I18n


class AsyncI18nDatabase(AsyncBaseDatabase):
    """
    CRUD operations for the I18n table - Asynchronous Version.
    """

    # ── Read ──────────────────────────────────────────────────────────────

    async def get(self, group: str, key: str, lang: str) -> Optional[I18n]:
        """
        Return the I18n row for *(group, key, lang)*, or None.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(I18n).where(
                    I18n.group == group,
                    I18n.key   == key,
                    I18n.lang  == lang.lower().strip(),
                )
            )
            row = result.scalar_one_or_none()

        if row is None:
            logger.debug(
                f"[DB] I18n not found: group='{group}' key='{key}' lang='{lang}'"
            )
        else:
            logger.debug(
                f"[DB] I18n get: group='{group}' key='{key}' lang='{lang}'"
            )
        return row

    async def get_value(self, group: str, key: str, lang: str) -> Optional[str]:
        """
        Return just the translated string for *(group, key, lang)*, or None.
        """
        row = await self.get(group, key, lang)
        return row.value if row is not None else None

    async def get_all_by_group_lang(self, group: str, lang: str) -> List[I18n]:
        """
        Return all rows for *(group, lang)*, ordered by key asynchronously.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(I18n)
                .where(
                    I18n.group == group,
                    I18n.lang  == lang.lower().strip(),
                )
                .order_by(I18n.key)
            )
            rows = result.scalars().all()

        logger.debug(
            f"[DB] I18n get_all_by_group_lang: "
            f"group='{group}' lang='{lang}' found={len(rows)}"
        )
        return list(rows)

    async def get_all_by_key(self, group: str, key: str) -> List[I18n]:
        """
        Return all language variants for *(group, key)*, ordered by lang.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(I18n)
                .where(I18n.group == group, I18n.key == key)
                .order_by(I18n.lang)
            )
            rows = result.scalars().all()

        logger.debug(
            f"[DB] I18n get_all_by_key: group='{group}' key='{key}' found={len(rows)}"
        )
        return list(rows)

    async def get_all_by_lang(self, lang: str) -> List[I18n]:
        """
        Return every row for *lang* across all groups asynchronously.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(I18n)
                .where(I18n.lang == lang.lower().strip())
                .order_by(I18n.group, I18n.key)
            )
            rows = result.scalars().all()

        logger.debug(
            f"[DB] I18n get_all_by_lang: lang='{lang}' found={len(rows)}"
        )
        return list(rows)

    async def get_all(self) -> List[I18n]:
        """
        Return every row ordered by group, key, lang asynchronously.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(I18n).order_by(I18n.group, I18n.key, I18n.lang)
            )
            rows = result.scalars().all()

        logger.debug(f"[DB] I18n get_all: found={len(rows)}")
        return list(rows)

    async def as_dict_for_group_lang(self, group: str, lang: str) -> Dict[str, str]:
        """
        Return {key: value} for all rows matching *(group, lang)*.
        """
        rows = await self.get_all_by_group_lang(group, lang)
        return {row.key: row.value for row in rows}

    async def list_groups(self) -> List[str]:
        """
        Return a sorted list of all distinct group names in the table.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(I18n.group).distinct().order_by(I18n.group)
            )
            groups = result.scalars().all()

        logger.debug(f"[DB] I18n groups: {groups}")
        return list(groups)

    async def list_supported_languages(self, group: Optional[str] = None) -> List[str]:
        """
        Return a sorted list of all language tags present in the table.
        """
        async with self.get_session() as session:
            stmt = select(I18n.lang).distinct()
            if group is not None:
                stmt = stmt.where(I18n.group == group)
            result = await session.execute(stmt.order_by(I18n.lang))
            langs = result.scalars().all()

        logger.debug(f"[DB] I18n supported languages (group={group!r}): {langs}")
        return list(langs)

    async def list_keys(self, group: str) -> List[str]:
        """
        Return a sorted list of all distinct keys within *group*.
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(I18n.key)
                .where(I18n.group == group)
                .distinct()
                .order_by(I18n.key)
            )
            keys = result.scalars().all()

        logger.debug(f"[DB] I18n keys for group='{group}': {keys}")
        return list(keys)

    async def find_missing(
        self, group: str, reference_lang: str = "zh"
    ) -> Dict[str, List[str]]:
        """
        Find keys that exist in *reference_lang* but are missing in other languages.
        """
        all_langs = await self.list_supported_languages(group)
        ref_keys  = set(await self.list_keys(group))

        missing: Dict[str, List[str]] = {}
        for lang in all_langs:
            if lang == reference_lang:
                continue            

            lang_rows = await self.get_all_by_group_lang(group, lang)
            lang_keys = {row.key for row in lang_rows}
            
            for key in ref_keys:
                if key not in lang_keys:
                    missing.setdefault(key, []).append(lang)

        logger.debug(
            f"[DB] I18n find_missing: group='{group}' "
            f"ref='{reference_lang}' missing_keys={len(missing)}"
        )
        return missing

    # ── Write ─────────────────────────────────────────────────────────────

    async def upsert(
        self,
        group:       str,
        key:         str,
        lang:        str,
        value:       str,
        description: Optional[str] = None,
    ) -> I18n:
        """
        Insert or update the row for *(group, key, lang)* asynchronously.
        """
        lang = lang.lower().strip()

        async with self.get_session() as session:
            result = await session.execute(
                select(I18n).where(
                    I18n.group == group,
                    I18n.key   == key,
                    I18n.lang  == lang,
                )
            )
            row = result.scalar_one_or_none()

            if row is None:
                row = I18n(
                    group       = group,
                    key         = key,
                    lang        = lang,
                    value       = value,
                    description = description,
                )
                session.add(row)
                logger.info(f"[DB] I18n created: [{lang}] {group}/{key}")
            else:
                row.value = value
                if description is not None:
                    row.description = description
                logger.info(f"[DB] I18n updated: [{lang}] {group}/{key}")
            
            # The context manager will automatically commit.

        return row

    async def upsert_many(self, rows: List[Dict]) -> Tuple[int, int]:
        """
        Bulk upsert multiple I18n rows asynchronously.
        """
        created = updated = 0

        async with self.get_session() as session:
            for item in rows:
                lang = item["lang"].lower().strip()
                result = await session.execute(
                    select(I18n).where(
                        I18n.group == item["group"],
                        I18n.key   == item["key"],
                        I18n.lang  == lang,
                    )
                )
                existing = result.scalar_one_or_none()

                if existing is None:
                    session.add(I18n(
                        group       = item["group"],
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
            f"[DB] I18n upsert_many: created={created} updated={updated}"
        )
        return created, updated

    async def delete(self, group: str, key: str, lang: str) -> bool:
        """
        Delete the row for *(group, key, lang)* asynchronously.
        """
        lang = lang.lower().strip()

        async with self.get_session() as session:
            result = await session.execute(
                select(I18n).where(
                    I18n.group == group,
                    I18n.key   == key,
                    I18n.lang  == lang,
                )
            )
            row = result.scalar_one_or_none()

            if row is None:
                logger.warning(
                    f"[DB] I18n.delete: not found [{lang}] {group}/{key}"
                )
                return False

            await session.delete(row)

        logger.info(f"[DB] I18n deleted: [{lang}] {group}/{key}")
        return True

    async def delete_all_for_lang(self, lang: str, group: Optional[str] = None) -> int:
        """
        Delete every row for *lang* asynchronously.
        """
        lang = lang.lower().strip()

        async with self.get_session() as session:
            stmt = select(I18n).where(I18n.lang == lang)
            if group is not None:
                stmt = stmt.where(I18n.group == group)
            
            result = await session.execute(stmt)
            rows = result.scalars().all()

            if not rows:
                logger.warning(
                    f"[DB] I18n.delete_all_for_lang: no rows for "
                    f"lang='{lang}' group={group!r}"
                )
                return 0

            count = len(rows)
            for row in rows:
                await session.delete(row)

        logger.info(
            f"[DB] I18n deleted all for lang='{lang}' group={group!r}: "
            f"count={count}"
        )
        return count
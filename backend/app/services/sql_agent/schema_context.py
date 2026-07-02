#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-30
# @description: Schema context builder with TTL cache and keyword-based table pre-filtering.
#
# Responsibilities
# ────────────────
# 1. Fetch get_schema / sample_data results and cache them with TTL.
# 2. Decide which tables to inject into the system prompt:
#    - schema has < TABLE_INJECT_THRESHOLD tables  →  inject ALL tables
#    - schema has >= TABLE_INJECT_THRESHOLD tables  →  keyword-match against user query first
# 3. Render the selected table info as a markdown block ready for prompt injection.

import json
import re
from typing import List, Dict, Any, Optional
from loguru import logger

from app.infra.cache.memory import MemoryCacheStore
from app.infra.cache.factory import create_cache_backend

# If a schema has fewer than this many tables, skip filtering and inject everything.
TABLE_INJECT_THRESHOLD = 10

# Default TTL values (seconds).  Schema structure is stable so we use a long
# TTL; sample data may drift slightly so we use a shorter one.
DEFAULT_SCHEMA_TTL  = 3600   # 1 hour
DEFAULT_SAMPLE_TTL  = 600    # 10 minutes

# Try importing jieba; if that fails, downgrade to pure English mode.
try:
    import jieba
    _JIEBA_AVAILABLE = True
except ImportError:
    _JIEBA_AVAILABLE = False
class SchemaContextBuilder:
    """
    Builds the table-context block that is injected into the system prompt.

    Parameters
    ----------
    sql_tools : SQLTools
        The tool instance used to call get_schema / sample_data.
    schema_name : str
        The DuckDB schema this agent is scoped to.
    cache : MemoryCacheStore
        Shared TTL-capable cache backend.
    schema_ttl : float
        Seconds before a cached schema entry is considered stale.
    sample_ttl : float
        Seconds before a cached sample entry is considered stale.
    sample_limit : int
        Number of sample rows to fetch per table.
    """

    def __init__(
        self,
        sql_tools,
        schema_name: str = "main",
        prompt_template_1:str=None,
        prompt_2:str=None,
        prompt_3:str=None,
        cache: Optional[MemoryCacheStore] = None,
        schema_ttl: float = DEFAULT_SCHEMA_TTL,
        sample_ttl:  float = DEFAULT_SAMPLE_TTL,
        sample_limit: int = 3,
    ):
        self._tools       = sql_tools
        self._schema      = schema_name
        self._prompt_template_1 = prompt_template_1 or self._default_prompt_template_1()
        self._prompt_2 = prompt_2 or self._default_prompt_2()
        self._prompt_3 = prompt_3 or self._default_prompt_3()
        self._cache       = cache or create_cache_backend(namespace="schema_context", max_size=256)
        self._schema_ttl  = schema_ttl
        self._sample_ttl  = sample_ttl
        self._sample_limit = sample_limit

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def build_context_block(self, user_query: str) -> str:
        """
        Return a markdown string describing the tables that are relevant to
        *user_query*.  This string is appended to the system prompt so the LLM
        already knows the schema and sample values before it starts reasoning.

        The method never raises: on any internal error it returns an empty
        string so the agent can still fall back to tool calls.
        """
        try:
            all_tables = self._list_tables()
            if not all_tables:
                logger.warning(f"No tables found in schema '{self._schema}'.")
                return ""

            # If the threshold is exceeded, a "check only table name" strategy will be adopted.
            only_names = False
            if len(all_tables) < TABLE_INJECT_THRESHOLD:
                selected = all_tables
                logger.debug(
                    f"[SchemaContext] {len(all_tables)} tables — injecting all."
                )
            else:
                selected = self._filter_by_keywords(user_query, all_tables)
                logger.debug(
                    f"[SchemaContext] {len(all_tables)} tables — "
                    f"keyword filter selected {len(selected)}: {selected}"
                )

            if not selected:
                selected = all_tables
                only_names = True
                logger.debug(f"[SchemaContext] Exceed threshold & no match. Rendering names only.")
            else:
                logger.debug(f"[SchemaContext] Keyword filter selected {len(selected)}: {selected}")

            return self._render(selected,only_names=only_names)

        except Exception as e:
            logger.error(f"[SchemaContext] build_context_block failed: {e}")
            return ""

    def invalidate(self, table_name: Optional[str] = None) -> None:
        """
        Evict cache entries.

        - table_name=None  →  evict everything for this schema
        - table_name given →  evict only that table's schema + sample entries
        """
        if table_name:
            keys = [
                self._schema_key(table_name),
                self._sample_key(table_name),
            ]
        else:
            prefix = f"schema_ctx:{self._schema}:"
            keys = list(self._cache.yield_keys(prefix=prefix))

        if keys:
            self._cache.mdelete(keys)
            logger.info(f"[SchemaContext] Cache invalidated: {keys}")

    # ──────────────────────────────────────────────────────────────────────
    # Cache helpers
    # ──────────────────────────────────────────────────────────────────────

    def _schema_key(self, table: str) -> str:
        return f"schema_ctx:{self._schema}:{table}:schema"

    def _sample_key(self, table: str) -> str:
        return f"schema_ctx:{self._schema}:{table}:sample"

    def _tables_key(self) -> str:
        return f"schema_ctx:{self._schema}:__tables__"

    def _cache_get(self, key: str):
        """Return the deserialized value or None if missing / expired."""
        results = self._cache.mget_ttl([key])
        raw = results[0]
        if raw is None:
            return None
        return json.loads(raw.decode("utf-8"))

    def _cache_set(self, key: str, value: Any, ttl: float) -> None:
        encoded = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self._cache.mset_with_ttl([(key, encoded)], ttl_seconds=ttl)

    # ──────────────────────────────────────────────────────────────────────
    # Data fetching (with cache)
    # ──────────────────────────────────────────────────────────────────────

    def _list_tables(self) -> List[Dict[str, str]]:
        """Return the list of user tables in the current schema (cached)."""
        key = self._tables_key()
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        
        table_infos = self._tools.list_tables_metadata(schema_name=self._schema)

        # Use schema TTL for the table list itself.
        self._cache_set(key, table_infos, self._schema_ttl)
        return table_infos

    def _get_schema(self, table: str) -> List[Dict[str, str]]:
        """Return column info for *table* (cached)."""
        key = self._schema_key(table)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        result = self._tools.get_schema(table, self._schema)
        if isinstance(result, dict) and "error" in result:
            logger.warning(f"[SchemaContext] get_schema error for {table}: {result}")
            return []

        self._cache_set(key, result, self._schema_ttl)
        return result

    def _get_sample(self, table: str) -> List[Dict[str, Any]]:
        """Return sample rows for *table* (cached)."""
        key = self._sample_key(table)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        result = self._tools.sample_data(table, self._schema, limit=self._sample_limit)
        if isinstance(result, dict) and "error" in result:
            logger.warning(f"[SchemaContext] sample_data error for {table}: {result}")
            return []

        self._cache_set(key, result, self._sample_ttl)
        return result

    # ──────────────────────────────────────────────────────────────────────
    # Keyword-based table pre-filtering  (used when tables >= threshold)
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """
        Extract meaningful tokens from a natural-language string.
        Supports both English and Chinese text.

        Strategy
        ────────
        1. Lower-case the whole string.
        2. Split Chinese and non-Chinese segments apart.
        3. For Chinese segments: use jieba word segmentation (if available),
        otherwise fall back to character-level tokenization.
        4. For non-Chinese segments: split on non-alphanumeric characters
        (handles CamelCase table names, normal English words, etc.).
        5. Discard very short tokens (≤ 2 chars for English; ≥ 1 char for Chinese).
        """
        text = text.lower()
        tokens: List[str] = []

        # Split into alternating non-Chinese / Chinese segments
        # Pattern matches a contiguous run of CJK Unified Ideographs
        segments = re.split(r'([\u4e00-\u9fff]+)', text)

        for segment in segments:
            if not segment:
                continue

            if re.search(r'[\u4e00-\u9fff]', segment):
                # ── Chinese segment ──────────────────────────────────────
                if _JIEBA_AVAILABLE:
                    # jieba.cut returns a generator of words
                    words = jieba.cut(segment, cut_all=False)
                    tokens.extend(w for w in words if len(w) >= 1)
                else:
                    # Fallback: single-character tokenization
                    tokens.extend(list(segment))
            else:
                # ── English / symbol segment ─────────────────────────────
                parts = re.split(r'[^a-z0-9]+', segment)
                tokens.extend(t for t in parts if len(t) > 2)

        return tokens

    def _filter_by_keywords(
        self, user_query: str, all_tables: List[Dict[str, str]]
    ) -> List[str]:
        """
        Return the subset of *all_tables* whose names share at least one token
        with *user_query*.

        Table names are also tokenized (e.g. "order_items" → ["order", "items"])
        so partial word matches work naturally.

        If nothing matches, an empty list is returned — the caller decides the
        fallback behaviour.
        """
        query_tokens = set(self._tokenize(user_query))
        matched = []

        for table in all_tables:
            table_name = table.get("name","")
            if table_name:
                table_info = table + " " + table.get("comment","")
                table_tokens = set(self._tokenize(table_info))
                if query_tokens & table_tokens:          # non-empty intersection
                    matched.append(table_name)

        return matched

    # ──────────────────────────────────────────────────────────────────────
    # Prompt rendering
    # ──────────────────────────────────────────────────────────────────────

    def _render(self, table_infos: List[Dict[str, str]],only_names: bool = False) -> str:
        """
        Build the markdown context block that will be appended to the system
        prompt.  Format::

            ## Pre-loaded Table Context
            ### `schema.table_a`
            **Schema** (column → type):
            | column | type |
            ...
            **Sample data** (3 rows):
            | col1 | col2 | ...
            ...
        """
        # ── Authoritative table list ──────────────────────────────────────
        # Placed at the very top of the block so the LLM sees it first and
        # is less likely to hallucinate table names from semantic association.
        display_names = []
        for t in table_infos:
            name_str = f"`{self._schema}.{t['name']}`"
            if t.get('comment'):
                name_str += f" ({t['comment']})"
            display_names.append(name_str)

        result = self._prompt_template_1.format(table_names=display_names)

        if only_names:
            return f"{result}\n{self._default_prompt_3}"            

        lines = []
        lines.append("\n---")
        for t in table_infos:
            table = t['name']
            comment = t.get('comment', 'No comment')
            schema_info = self._get_schema(table)
            sample_rows = self._get_sample(table)

            lines.append(f"### Table: `{self._schema}.{table}`")
            lines.append(f"**Description**: {comment}")

            # --- Schema table ---
            if schema_info:
                lines.append("**Schema** (column → type):")
                lines.append("| column | type |")
                lines.append("|--------|------|")
                for col in schema_info:
                    lines.append(f"| {col['column']} | {col['type']} |")
            else:
                lines.append("_Schema unavailable._")

            lines.append("")  # blank line

            # --- Sample data table ---
            if sample_rows:
                cols = list(sample_rows[0].keys())
                lines.append(f"**Sample data** ({len(sample_rows)} rows):")
                lines.append("| " + " | ".join(cols) + " |")
                lines.append("|" + "|".join(["---"] * len(cols)) + "|")
                for row in sample_rows:
                    cells = [str(row.get(c, "")) for c in cols]
                    lines.append("| " + " | ".join(cells) + " |")
            else:
                lines.append("_Sample data unavailable._")

            lines.append("")  # blank line between tables

            detail_info = "\n".join(lines)
            result = f"{result}\n{self._prompt_2}{detail_info}"
        return result
    
    def _default_prompt_template_1(self):
        return """
## Pre-loaded Table Context
### IMPORTANT: Authoritative table list
The tables that actually exist in this database are listed below.

Available tables:{table_names}
        """
    
    def _default_prompt_2(self):
        return """
The following section contains column definitions and sample rows for each table. Use them directly.
        """
    
    def _default_prompt_3(self):
        return """
Due to the large number of tables, the detailed table structure is not listed directly. 
        """

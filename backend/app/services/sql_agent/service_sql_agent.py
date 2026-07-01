#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-03
# @description: SQLAgent Service — builds and caches SQLAgent instances
#               from LLM config stored in the database, with i18n prompt support.
#
# Design
# ──────
#  SQLAgentService owns a Dict[llm_provider_id, SQLAgent] cache.
#  On first call for a given llm_provider_id the service:
#    1. resolves the LLM row via the LLM table (llm_provider_id)
#    2. builds an AgentLLM from the resolved config
#    3. constructs SQLAgent(llm, tools, schema_name, system_prompt_template, tool_schema)
#    4. stores it in _agent_cache
#  Subsequent calls with the same llm_provider_id + schema_name hit the cache.
#
#  Cache invalidation
#  ──────────────────
#  Call invalidate(llm_provider_id, schema_name) to evict a single agent.
#  Call invalidate_all() to clear everything.

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from loguru import logger

from app.runtime.cache.lazy_cache import AsyncLazyCache

from .agent import SQLAgent,SQLAgentConfig
from .tool import SQLTools
from .manager import DBManager

from app.infra.db.database import Tool

if TYPE_CHECKING:
    from app.core.service_container import ServiceContainer

# Cache key: (llm_provider_id, schema_name)
_CacheKey = Tuple[int, str]

class SQLAgentService:
    """
    Application-level service that manages SQLAgent instances.

    Lifecycle
    ─────────
    Instantiated once inside ServiceContainer and held at
    ``container.sql_agent_service``.  Each agent is lazily built on the first
    ``run()`` call for a (llm_provider_id, schema_name) pair and then cached.

    Thread / concurrency safety
    ───────────────────────────
    A per-key asyncio.Lock prevents the thundering-herd problem: if two
    coroutines request the same agent simultaneously, only one builds it
    while the other awaits the lock.
    """

    def __init__(self, container: "ServiceContainer") -> None:
        self._container  = container
        self._llm_db     = container.llm_db
        self._prompt_db    = container.prompt_db
        self._setting_db = container.setting_db
        self._tool_db    = container.tool_db
        
        from app.infra.db.duckdb_manager import duckdb_manager
        self._duckdb_manager = duckdb_manager
        # DBManager wraps the same DuckDB connection for CSV import operations
        self._db_manager = DBManager(duckdb_manager=self._duckdb_manager)

        self._agent_cache = AsyncLazyCache[_CacheKey, SQLAgent](
            builder=self._build_agent,
            name="sql_agent",
            description="(llm_provider_id, schema_name) → SQLAgent",
        )
        container.cache_registry.register(
            self._agent_cache.name,
            self._agent_cache,
            key_codec=lambda raw: (raw[0], raw[1]) if isinstance(raw, (list, tuple)) else raw,
        )
        
        # per-key build locks
        self._build_locks: Dict[_CacheKey, asyncio.Lock] = {}

    # ── Public API ────────────────────────────────────────────────────────

    async def run(
        self,
        user_query: str,
        llm_provider_id: int = 1,
        schema_name: str = "main",
        tool_name: str = "",
    ) -> str:
        """
        Execute a natural-language data query using the configured SQLAgent.

        Parameters
        ──────────
        user_query : str
            The natural-language question from the user.
        llm_provider_id : int
            ID of the LLM row in the database whose config drives the agent.
        schema_name : str
            DuckDB schema the agent should operate within (default: "main").

        Returns
        ───────
        str
            Final natural-language answer produced by the agent.

        Raises
        ──────
        ValueError
            If the LLM row does not exist or is inactive.
        """
        agent = await self._agent_cache.get_or_build(
            (llm_provider_id, schema_name), llm_provider_id, schema_name, tool_name
        )
        # run() is synchronous in the original SQLAgent implementation;
        # wrap it in asyncio.to_thread so we don't block the event loop.
        return await asyncio.to_thread(agent.run, user_query)

    async def import_csv(
        self,
        file_path: str,
        schema_name: str = "main",
        table_name: Optional[str] = None,
        primary_key: str | list[str] = None,
        force_cast: bool = False,
        allow_new_columns: bool = False,
    ) -> str:
        """
        Import a CSV file into DuckDB via DBManager.

        Delegates entirely to ``DBManager.import_csv``; wrapped in
        ``asyncio.to_thread`` so the pandas/DuckDB I/O does not block the
        event loop.

        Parameters
        ──────────
        file_path : str
            Absolute path to the CSV file on disk.
        schema_name : str
            Target DuckDB schema (default: "main").
        table_name : str | None
            Target table name; derived from the filename when omitted.
        primary_key : str | None
            Column name used for UPSERT conflict resolution.
            When None, rows are appended (may produce duplicates).
        force_cast : bool
            When True, allow type-mismatched columns to be cast silently.
        allow_new_columns : bool
            When True, add columns present in the CSV but absent in the
            existing table instead of raising an error.

        Returns
        ───────
        str
            Fully-qualified table path, e.g. ``"main"."sales_tbl"``.

        Raises
        ──────
        ValueError
            On column / primary-key mismatches (propagated from DBManager).
        TypeError
            On unresolvable type conflicts (propagated from DBManager).
        """
        logger.info(
            f"[SQLAgentService] import_csv  file={file_path!r}  "
            f"schema={schema_name!r}  table={table_name!r}  pk={primary_key!r}"
        )
        return await asyncio.to_thread(
            self._db_manager.import_csv,
            file_path,
            schema_name,
            table_name,
            primary_key,
            force_cast,
            allow_new_columns,
        )

    async def _build_agent(
        self, key: _CacheKey, llm_provider_id: int, schema_name: str, tool_name: str
    ) -> SQLAgent:
        """Load LLM config + prompts from DB and construct a SQLAgent."""

        # ── 1. Resolve LLM config ────────────────────────────────────────
        llm_config = await self._llm_db.get(llm_id=llm_provider_id)
        if llm_config is None:
            raise ValueError(
                f"LLM provider id={llm_provider_id!r} not found in database."
            )

        # ── 2. Build AgentLLM from config ────────────────────────────────
        from app.infra.llm import LLMClient, AgentLLM  # local import to avoid circular deps
        client = LLMClient(
            base_url=llm_config.base_url,
            api_key=llm_config.api_key,
            temperature=0,
        )

        # ── 3. Build SQLTools (wraps the global DuckDB connection) ────────
        sql_tools = SQLTools(
            duckdb_manager=self._duckdb_manager,
            schema_name=schema_name,
        )

        # ── 4. Optionally resolve Tool row ───────────────────────────────
        tool: Optional[Tool] = None
        if tool_name:
            tool = await self._tool_db.get_by_name(tool_name)
            if tool is None:
                raise ValueError(f"Tool {tool_name!r} not found in database.")
            if not tool.is_active:
                raise ValueError(f"Tool {tool_name!r} is inactive.")
            
        # ── 5. Load prompts via PromptLoader ────────────────────────
        from app.core.prompt_loader import prompt_loader
        system_prompt_template = prompt_loader.get("sql_agent.system_prompt_template") or None
        agent_llm_tool_schema_template = prompt_loader.get("agent_llm.tool_schema") or None

        schema_context_prompt_template_1 = prompt_loader.get("sql_agent.schema_context_prompt_template_1") or None
        schema_context_prompt_2 = prompt_loader.get("sql_agent.schema_context_prompt_2") or None
        schema_context_prompt_3 = prompt_loader.get("sql_agent.schema_context_prompt_3") or None
        get_schema_desc = prompt_loader.get("sql_agent.get_schema.desc") or None
        sample_data_desc = prompt_loader.get("sql_agent.sample_data.desc") or None
        execute_sql_desc = prompt_loader.get("sql_agent.execute_sql.desc") or None
        run_python_desc = prompt_loader.get("sql_agent.run_python.desc") or None
        para_table_name_desc = prompt_loader.get("sql_agent.tool.table_name.desc") or None
        para_limit_desc = prompt_loader.get("sql_agent.tool.limit.desc") or None
        para_sql_desc = prompt_loader.get("sql_agent.tool.sql.desc") or None
        para_code_desc = prompt_loader.get("sql_agent.tool.code.desc") or None

        sql_agent_config = SQLAgentConfig(
            schema_name=schema_name,   
            system_prompt_template=system_prompt_template,
            schema_context_prompt_template_1=schema_context_prompt_template_1,  
            schema_context_prompt_2=schema_context_prompt_2,
            schema_context_prompt_3=schema_context_prompt_3,    
            get_schema_desc=get_schema_desc,
            sample_data_desc=sample_data_desc,  
            execute_sql_desc=execute_sql_desc,
            run_python_desc=run_python_desc,    
            para_table_name_desc=para_table_name_desc,
            para_limit_desc=para_limit_desc,    
            para_sql_desc=para_sql_desc,
            para_code_desc=para_code_desc,  
        )

        # ── 6. Construct and return SQLAgent ─────────────────────────────
        logger.debug(
            f"[SQLAgentService] building agent  "
            f"llm_provider_id={llm_provider_id}  schema={schema_name!r} "
        )
        llm = AgentLLM(client=client, 
            model=llm_config.model_name,
            tool_prompt_template=agent_llm_tool_schema_template)
        return SQLAgent(
            llm=llm,
            tools=sql_tools,
            config=sql_agent_config,
        )

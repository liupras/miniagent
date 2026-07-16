#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author   : Liu Lijun
# @date     : 2026-07-15
# @description: Class-based Factory to wrap SQLTools as StructuredTools in langchain

import asyncio
from typing import List
from pydantic import create_model, Field
from langchain_core.tools import StructuredTool

from .sql_tools import SQLTools
from .models import SQLAgentConfig

class LocalizedSQLToolFactory:
    """
    Localization tool factory class: specifically responsible for dynamically building a strongly typed LangChain toolkit at runtime based on the current language context.
    """

    _DEFAULT_DESCS = {
        "get_schema": (
            "Retrieves the structure information (column names, data types) of a specified table in a database. "
            "This tool must be called before writing any SQL if the table structure is not explicitly known."
        ),
        "sample_data": (
            "Retrieves sample data from the table. Use this when you need to understand the specific range of values, "
            "enumeration value format, or data characteristics of a field."
        ),
        "execute_sql": (
            "Execute SQL queries in DuckDB. Only SELECT statements are allowed. "
            "Please ensure that you have verified the table and column names using get_schema before calling this tool."
        ),
        "run_python": (
            "\nExecute Python code in a secure sandbox for data analysis and visualisation tasks that are hard to express in SQL alone.\n"
            "Use cases: statistical summaries, pivot tables, correlation matrices, data cleaning, chart generation (matplotlib/seaborn), or any pandas/numpy transformation.\n\n"
            "The sandbox provides:\n"
            "- `conn`        : read-only DuckDB connection (SELECT/WITH only)\n"
            "- `schema_name` : current schema name string\n"
            "- Allowed imports: math, statistics, random, json, re, datetime, decimal, collections, itertools, functools, pandas, numpy, io, string, matplotlib, matplotlib.pyplot, plt, seaborn, sns, base64\n\n"
            "Example – fetch data then analyse:\n"
            "```python\n"
            "import pandas as pd\n"
            "df = conn.execute(f'SELECT * FROM {schema_name}.sales LIMIT 10000').fetchdf()\n"
            "print(df.describe())\n"
            "df.groupby('region')['revenue'].sum()\n"
            "```\n\n"
            "Rules:\n"
            "- No file I/O, no os/sys/subprocess, no network calls.\n"
            "- Only SELECT queries allowed through `conn`.\n"
            "- Execution is time-limited to 10 seconds.\n"
            "- For charts: Use `import matplotlib; matplotlib.use('Agg')` first.\n"
            "- DO NOT call `plt.show()`. Instead, end your code with `plt.gcf()` to return the image.\n"
            "- The value of the last expression is returned as `result`.\n\n"
        ),
        "para_table_name": "Table name.",
        "para_limit": "The number of rows returned defaults to 3.",
        "para_sql": "A complete SQL SELECT statement that conforms to DuckDB syntax.",
        "para_code": (
            "Python source code to execute. Use `conn` to query DuckDB. "
            "Use `print()` for text output. The last expression's value is captured automatically."
        )
    }

    def __init__(self, 
        sql_tools: SQLTools,
        config:SQLAgentConfig, 
        schema_name: str = "main"
    ):

        self.sql_tools = sql_tools
        self.schema_name = schema_name
        self._config = config

    def _get_schema_sync(self, table_name: str) -> str:
        return str(self.sql_tools.get_schema(table_name=table_name, schema_name=self.schema_name))

    async def _get_schema_async(self, table_name: str) -> str:
        return await asyncio.to_thread(self._get_schema_sync, table_name)

    def _sample_data_sync(self, table_name: str, limit: int = 3) -> str:
        return str(self.sql_tools.sample_data(table_name=table_name, schema_name=self.schema_name, limit=limit))

    async def _sample_data_async(self, table_name: str, limit: int = 3) -> str:
        return await asyncio.to_thread(self._sample_data_sync, table_name, limit)

    def _execute_sql_sync(self, sql: str) -> str:
        return str(self.sql_tools.execute_sql(sql=sql))

    async def _execute_sql_async(self, sql: str) -> str:
        return await asyncio.to_thread(self._execute_sql_sync, sql)

    def _run_python_sync(self, code: str) -> str:
        return str(self.sql_tools.run_python(code=code))

    async def _run_python_async(self, code: str) -> str:
        return await asyncio.to_thread(self._run_python_sync, code)

    def build(self) -> List[StructuredTool]:
        """
        The build is performed within the coroutine/thread of the current request. Calling t() at this point will accurately capture the language identifier of the current context.
        """

        p_table_name_desc = self._config.para_table_name_desc or self._DEFAULT_DESCS["para_table_name"]
        p_limit_desc = self._config.para_limit_desc or self._DEFAULT_DESCS["para_limit"]
        p_sql_desc = self._config.para_sql_desc or self._DEFAULT_DESCS["para_sql"]
        p_code_desc = self._config.para_code_desc or self._DEFAULT_DESCS["para_code"]
        
        GetSchemaArgs = create_model(
            'GetSchemaArgs',
            table_name=(str, Field(description=p_table_name_desc))
        )

        SampleDataArgs = create_model(
            'SampleDataArgs',
            table_name=(str, Field(description=p_table_name_desc)),
            limit=(int, Field(default=3, description=p_limit_desc))
        )

        ExecuteSQLArgs = create_model(
            'ExecuteSQLArgs',
            sql=(str, Field(description=p_sql_desc))
        )

        RunPythonArgs = create_model(
            'RunPythonArgs',
            code=(str, Field(description=p_code_desc))
        )

        return [
            StructuredTool.from_function(
                func=self._get_schema_sync,
                coroutine=self._get_schema_async,
                name="get_schema",
                description=self._config.get_schema_desc or self._DEFAULT_DESCS["get_schema"], 
                args_schema=GetSchemaArgs
            ),
            StructuredTool.from_function(
                func=self._sample_data_sync,
                coroutine=self._sample_data_async,
                name="sample_data",
                description=self._config.sample_data_desc or self._DEFAULT_DESCS["sample_data"],
                args_schema=SampleDataArgs
            ),
            StructuredTool.from_function(
                func=self._execute_sql_sync,
                coroutine=self._execute_sql_async,
                name="execute_sql",
                description=self._config.execute_sql_desc or self._DEFAULT_DESCS["execute_sql"],
                args_schema=ExecuteSQLArgs
            ),
            StructuredTool.from_function(
                func=self._run_python_sync,
                coroutine=self._run_python_async,
                name="run_python",
                description=self._config.run_python_desc or self._DEFAULT_DESCS["run_python"],
                args_schema=RunPythonArgs
            )
        ]
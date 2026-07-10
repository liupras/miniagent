#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-30
# @description: sql agent

import json
from dataclasses import dataclass
from typing import Optional

from .schema_context import SchemaContextBuilder
from app.runtime.llm.agent_client import AgentLLM

@dataclass
class SQLAgentConfig:
    schema_name: str = "main"

    # prompts
    system_prompt_template: Optional[str] = None
    schema_context_prompt_template_1: Optional[str] = None
    schema_context_prompt_2: Optional[str] = None
    schema_context_prompt_3: Optional[str] = None

    # tool    
    get_schema_desc: Optional[str] = None
    sample_data_desc: Optional[str] = None
    execute_sql_desc: Optional[str] = None
    run_python_desc: Optional[str] = None
    para_table_name_desc: Optional[str] = None
    para_limit_desc: Optional[str] = None
    para_sql_desc: Optional[str] = None
    para_code_desc: Optional[str] = None

class SQLAgent:
    def __init__(self, llm:AgentLLM, tools, config:SQLAgentConfig):
        self.llm = llm
        self.tools = tools
        self._config = config
        self._schema_name = config.schema_name or "main"
        self._get_schema_desc = config.get_schema_desc or self._default_get_schema_desc()
        self._sample_data_desc = config.sample_data_desc or self._default_sample_data_desc()
        self._execute_sql_desc = config.execute_sql_desc or self._default_execute_sql_desc()
        self._run_python_desc = config.run_python_desc or self._default_run_python_desc()
        self._para_table_name_desc = config.para_table_name_desc or self._default_para_table_name_desc()
        self._para_limit_desc = config.para_limit_desc or self._default_para_limit_desc()
        self._para_sql_desc = config.para_sql_desc or self._default_para_sql_desc()
        self._para_code_desc = config.para_code_desc or self._default_para_code_desc()

        _system_prompt_template = config.system_prompt_template or self._default_system_prompt_template()
        self._system_prompt =  _system_prompt_template.format(schema_name=self._schema_name) 
     
        self._tool_schema = self._build_tool_schema(
            get_schema_desc=self._get_schema_desc, 
            sample_data_desc=self._sample_data_desc,
            execute_sql_desc=self._execute_sql_desc,
            run_python_desc=self._run_python_desc,
            para_table_name_desc=self._para_table_name_desc,
            para_limit_desc=self._para_limit_desc,
            para_sql_desc=self._para_sql_desc,
            para_code_desc=self._para_code_desc
        )

        self._ctx_builder = SchemaContextBuilder(
            sql_tools=tools,
            schema_name=self._schema_name,
            prompt_template_1=config.schema_context_prompt_template_1,
            prompt_2=config.schema_context_prompt_2,
            prompt_3=config.schema_context_prompt_3
        )

    async def run(self, user_query: str):
        # 1. Build the table-context block (cached; cheap on repeated calls).
        #    This replaces the first 1-2 tool-call round trips in the old flow.
        context_block = self._ctx_builder.build_context_block(user_query)

        # 2. Compose the system prompt: base prompt + injected table context.
        if context_block:
            full_system_prompt = self._system_prompt + "\n\n" + context_block
        else:
            # Context builder failed or returned nothing; use base prompt so
            # the agent can still fall back to get_schema / sample_data tools.
            full_system_prompt = self._system_prompt

        messages = [
            {"role": "system", "content": full_system_prompt},
            {"role": "user",   "content": user_query},
        ]

        for step in range(10):  # Up to 10 rounds of tool calls
            response = await self.llm.achat(messages=messages,tool_schema=self._tool_schema)

            # =========================
            # 1. If it's a tool call
            # =========================
            if response.get("tool_calls"):

                # Add the assistant's response (including the tool_calls intent).
                messages.append({
                    "role": "assistant",
                    #"tool_calls": response["tool_calls"], # Includes complete call ID and parameters
                    "content": response.get("content", "") # Ensure it is not None
                })

                for tool_call in response["tool_calls"]:
                    t_name = tool_call["function"]["name"]
                    t_args = tool_call["function"]["arguments"]
                    t_id = tool_call["id"]

                    # Automatic injection of private variable schema_name
                    if t_name in ["get_schema", "sample_data"]:
                        t_args["schema_name"] = self._schema_name 

                    result = self.tools.call_tool(t_name, t_args)

                    # Add a corresponding tool role message for each tool call.
                    messages.append({
                        "role": "tool",
                        "tool_call_id": t_id,
                        "content": json.dumps(result, ensure_ascii=False)
                    })

            # =========================
            # 2. If this is the final answer
            # =========================
            else:
                return response["content"]

        return "Unable to complete the query within the limit number of steps"
    
    def _default_get_schema_desc(self):
        return "Retrieves the structure information (column names, data types) of a specified table in a database. This tool must be called before writing any SQL if the table structure is not explicitly known."
    
    def _default_sample_data_desc(self):
        return "Retrieves sample data from the table. Use this when you need to understand the specific range of values, enumeration value format, or data characteristics of a field."
    
    def _default_execute_sql_desc(self):
        return "Execute SQL queries in DuckDB. Only SELECT statements are allowed. Please ensure that you have verified the table and column names using get_schema before calling this tool."
    
    def _default_run_python_desc(self):
        return """
Execute Python code in a secure sandbox for data analysis and visualisation tasks that are hard to express in SQL alone.
Use cases: statistical summaries, pivot tables, correlation matrices, data cleaning, chart generation (matplotlib/seaborn), or any pandas/numpy transformation.

The sandbox provides:
- `conn`        : read-only DuckDB connection (SELECT/WITH only)
- `schema_name` : current schema name string
- Allowed imports: math, statistics, random, json, re, datetime, decimal, collections, itertools, functools, pandas, numpy, numpy, io, string, matplotlib, matplotlib.pyplot, plt, seaborn, sns, base64

Example – fetch data then analyse:
```python

import pandas as pd
df = conn.execute(f'SELECT * FROM {schema_name}.sales LIMIT 10000').fetchdf()
print(df.describe())
df.groupby('region')['revenue'].sum()
```

Rules:
- No file I/O, no os/sys/subprocess, no network calls.
- Only SELECT queries allowed through `conn`.
- Execution is time-limited to 10 seconds.
- For charts: Use `import matplotlib; matplotlib.use('Agg')` first.
- DO NOT call `plt.show()`. Instead, end your code with `plt.gcf()` to return the image.
- The value of the last expression is returned as `result`.

""" 

    def _default_para_table_name_desc(self):
        return "Table name."
    
    def _default_para_limit_desc(self):
        return "The number of rows returned defaults to 3."
    
    def _default_para_sql_desc(self):
        return "A complete SQL SELECT statement that conforms to DuckDB syntax."

    def _default_para_code_desc(self):
        return (
            "Python source code to execute. "
            "Use `conn` to query DuckDB. "
            "Use `print()` for text output. "
            "The last expression's value is captured automatically."
        )
    
    def _build_tool_schema(self,
        get_schema_desc:str,
        sample_data_desc:str,
        execute_sql_desc:str,
        run_python_desc:str,
        para_table_name_desc:str,
        para_limit_desc:str,
        para_sql_desc:str,
        para_code_desc:str
    ):
        return  [
            {
                "type": "function",
                "function": {
                    "name": "get_schema",
                    "description": get_schema_desc,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string", 
                                "description": para_table_name_desc
                            }
                        },
                        "required": ["table_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "sample_data",
                    "description": sample_data_desc,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": para_table_name_desc
                            },
                            "limit": {
                                "type": "integer",
                                "description": para_limit_desc,
                                "default": 3
                            }
                        },
                        "required": ["table_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_sql",
                    "description": execute_sql_desc,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sql": {
                                "type": "string",
                                "description": para_sql_desc
                            }
                        },
                        "required": ["sql"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_python",
                    "description": run_python_desc,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": para_code_desc
                            }
                        },
                        "required": ["code"]
                    }
                }
            }
        ]
       
    
    def _default_system_prompt_template(self):
        return """
You are a data analysis agent using DuckDB to query data,The current database schema is: `{schema_name}`

Rules:
1. All SQL must use the schema prefix: `{schema_name}.table_name`.
2. You only need to focus on the data under `{schema_name}`, and do not attempt to access other schemas.
3. Never guess column names. If you do not know the table structure, you must first call `get_schema`.
4. If you need to know the field values, call `sample_data`.
5. Use `execute_sql` for simple queries; use `run_python` when pandas/numpy add value.
6. Do not mix tool purposes: if a task is purely SQL, don't use `run_python`.
7. When writing SQL:
- Only SELECT statements are allowed.
- Must be based on the actual schema.
- Keep it as simple as possible.
- The SQL must be executable.
- Do not make up field names.

Response Process:
- Analyze the problem.
- Call the necessary tools (one or more rounds).
- Finally, provide a natural language explanation.
        """
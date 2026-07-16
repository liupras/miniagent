#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-30
# @description: sql agent

import json
from typing import AsyncGenerator, Dict, Any

from app.runtime.types import MessageRole
from app.runtime.llm.agent_client import AgentLLM

from .sql_tools import SQLTools
from .schema_context import SchemaContextBuilder
from .sql_tool_bridge import LocalizedSQLToolFactory
from app.runtime.agent.react_agent import ToolReActAgent
from .models import SQLAgentConfig

class SQLAgent:
    def __init__(self, 
        llm:AgentLLM, 
        tools:SQLTools, 
        config:SQLAgentConfig
    ):
        """
        SQLAgent is the core driver class.
        It dynamically assembles localized tools at runtime and parses the underlying state stream, exposing clean, semantic event traces downstream.
        """
        self.llm = llm
        self._tools = tools
        self._config = config
        self._schema_name = config.schema_name or "main"

        _system_prompt_template = config.system_prompt_template or self._default_system_prompt_template()
        self._base_system_prompt =  _system_prompt_template.format(schema_name=self._schema_name)

        self._ctx_builder = SchemaContextBuilder(
            sql_tools=tools,
            schema_name=self._schema_name,
            prompt_template_1=config.schema_context_prompt_template_1,
            prompt_2=config.schema_context_prompt_2,
            prompt_3=config.schema_context_prompt_3
        )

    async def astream(self, user_query: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Asynchronous generator: Captures the ReAct state loop, incrementally parses it, and pushes the structured execution trajectory to the front end in real time.
        """
        tool_factory = LocalizedSQLToolFactory(
            sql_tools=self._tools,
            schema_name=self._schema_name,
            config=self._config
          )
        localized_tools = tool_factory.build()

        # Build the schema context in advance and assemble the complete System Prompt.
        context_block = self._ctx_builder.build_context_block(user_query)
        full_system_prompt = self._base_system_prompt + "\n\n" + context_block if context_block else self._base_system_prompt

        # Inject the complete full_system_prompt directly as a system instruction into the Agent executor.
        react_executor = ToolReActAgent(
            agent_llm=self.llm,
            tools=localized_tools,
            system_instruction=full_system_prompt
        )

        inputs = {
            "messages": [
                {"role": MessageRole.USER, "content": user_query}
            ]
        }

        # Track the number of messages sent to calculate the delta.
        sent_message_count = len(inputs["messages"])

        # Drives the underlying ReAct step flow, parsing and generating semantic events.
        async for state in react_executor.astream(inputs):
            messages = state.get("messages", [])
            if len(messages) <= sent_message_count:
                continue

            # Filter and extract newly added messages
            new_messages = messages[sent_message_count:]
            sent_message_count = len(messages)

            for msg in new_messages:

                role = None
                content = ""
                tool_calls = []
                tool_call_id = None
                name = None

                if hasattr(msg, "type"):  # LangChain BaseMessage instances (AIMessage, ToolMessage, etc.)
                    msg_type = msg.type
                    content = msg.content
                    if msg_type == "ai":
                        role = MessageRole.ASSISTANT
                        tool_calls = getattr(msg, "tool_calls", [])
                    elif msg_type == "tool":
                        role = MessageRole.TOOL
                        tool_call_id = getattr(msg, "tool_call_id", None)
                        name = getattr(msg, "name", None)
                elif isinstance(msg, dict):  # Classic Dict Structure
                    role = msg.get("role")
                    content = msg.get("content", "")
                    tool_calls = msg.get("tool_calls", [])
                    tool_call_id = msg.get("tool_call_id")
                    name = msg.get("name")

                if role == MessageRole.ASSISTANT:
                    # A. Determine to invoke tool events
                    if "tool_calls":
                        parsed_tools = []
                        for tc in tool_calls:
                            # Compatible with LangChain tool format and OpenAI API classic format
                            tc_id = tc.get("id")
                            tc_name = tc.get("name") or tc.get("function", {}).get("name")
                            tc_args = tc.get("args") or tc.get("function", {}).get("arguments")
                            
                            parsed_tools.append({
                                "id": tc_id,
                                "name": tc_name,
                                "arguments": tc_args
                            })

                        yield {
                            "event": "tool_start",
                            "data": {
                                "tools": parsed_tools
                            }
                        }
                    # B. Final text response event
                    else:
                        yield {
                            "event": "final_answer",
                            "data": {"content": content}
                        }

                elif role == MessageRole.TOOL:
                    # C. Once the tool has finished executing, it returns the observation results.   
                    try:
                        observation = json.loads(content) if isinstance(content, str) else content
                    except Exception:
                        observation = content

                    yield {
                        "event": "tool_end",
                        "data": {
                            "tool_call_id": tool_call_id,
                            "name": name,
                            "output": observation
                        }
                    }

    async def run(self, user_query: str):
        """
        Synchronous compatible execution interface: directly consumes the astream and extracts the final final_answer.
        """
        final_content = ""
        async for event in self.astream(user_query):
            if event["event"] == "final_answer":
                final_content = event["data"]["content"]
        return final_content    
   
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
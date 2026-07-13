#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-10
# @description: React Agent

import json
from typing import AsyncGenerator, List, Dict, Any, Optional, Tuple
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from loguru import logger

from app.runtime.llm.agent_client import AgentLLM
from app.core.i18n.i18n import t
from app.runtime.types import MessageRole


class ToolReActAgent(Runnable[Dict[str, Any], Dict[str, Any]]):
    """
    Inheriting from Runnable, it explicitly declares both input and output types as Dict[str, Any].
    """
    def __init__(self, agent_llm: AgentLLM, tools: List[BaseTool], system_instruction: str = ""):
        """
        A generic asynchronous ReAct Agent compatible with the LCEL/LangGraph interface specification
        """
        super().__init__()
        self.agent_llm = agent_llm
        self.system_instruction = system_instruction
        self.tools_map = {tool.name: tool for tool in tools}
        self.tool_schemas = [convert_to_openai_tool(t) for t in tools] if tools else None

    async def ainvoke(self, input: Dict[str, Any], config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
        """Implement the asynchronous call interface of Runnable, and internally reuse the final state of astream."""
        final_state = None
        async for state in self.astream(input, config):
            final_state = state
        return final_state
        
    async def astream(
        self, 
        input: Dict[str, Any], 
        config: Optional[RunnableConfig] = None, 
        **kwargs: Any  # 💡 Cleverly retaining **kwargs allows for the silent "swallowing" of stream_mode="values" passed from the upper layer.
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        A simplified version of astream: unconditionally performs streaming responses according to the values ​​pattern (displaying the complete history).
        """
        # 1. Retrieving pure dictionary history messages
        messages, max_steps = self._prepare_context(input, config)

        # 2. ReAct Core Loop
        for step in range(max_steps):
            response_dict = await self.agent_llm.achat(messages, tool_schema=self.tool_schemas)

            response_dict = self._normalize_response(response_dict)
                
            messages.append(response_dict)
   
            yield {"messages": messages}

            if "tool_calls" not in response_dict:
                break

            for tool_call in response_dict["tool_calls"]:
                func_info = tool_call.get("function", {})
                tool_name = func_info.get("name")
                tool_args = func_info.get("arguments", {})

                success, tool_args = self._parse_tool_arguments(func_info.get("arguments", {}))
                if not success:
                    continue

                observation = await self._execute_tool_async(tool_name, tool_args)

                messages.append({
                    "role": MessageRole.TOOL,
                    "tool_call_id": tool_call.get("id", "call_idx"),
                    "name": tool_name,
                    "content": str(observation)
                })                
  
            yield {"messages": messages}
        else:
            self._handle_max_steps_error(messages)            
            yield {"messages": messages}

    def invoke(self, input: Dict[str, Any], config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
        """Pure synchronous execution loop"""

        messages, max_steps = self._prepare_context(input, config)

        for step in range(max_steps):
            response_dict = self.agent_llm.chat(messages, tool_schema=self.tool_schemas)
            
            response_dict = self._normalize_response(response_dict)
                
            messages.append(response_dict)

            if "tool_calls" not in response_dict:
                break

            for tool_call in response_dict["tool_calls"]:
                func_info = tool_call.get("function", {})
                tool_name = func_info.get("name")
                
                success, tool_args = self._parse_tool_arguments(func_info.get("arguments", {}))
                if not success:
                    continue

                observation = self._execute_tool_sync(tool_name, tool_args)

                messages.append({
                    "role": MessageRole.TOOL,
                    "tool_call_id": tool_call.get("id", "call_idx"),
                    "name": tool_name,
                    "content": observation
                })
        else:
            self._handle_max_steps_error(messages)

        return {"messages": messages}
    
    def _normalize_response(self, response_dict: Dict[str, Any]) -> Dict[str, Any]:
        """The return result of the standardized large model: ensure that the role exists and that the parameters of tool_calls conform to the standard string specification."""
        # 1. Fill in the missing role
        if "role" not in response_dict:
            response_dict["role"] = MessageRole.ASSISTANT
            
        # 2. Casts dict-type utility arguments to standard JSON strings.
        if "tool_calls" in response_dict:
            for tool_call in response_dict["tool_calls"]:
                func_info = tool_call.get("function", {})
                if "arguments" in func_info and isinstance(func_info["arguments"], dict):
                    func_info["arguments"] = json.dumps(func_info["arguments"], ensure_ascii=False)
                    
        return response_dict

    def _prepare_context(self, input: Dict[str, Any], config: Optional[RunnableConfig]) -> Tuple[List[Dict[str, Any]], int]:
        """Initialize historical messages, inject system prompts, and parse the maximum step limit."""
        messages = list(input.get("messages", []))
        if self.system_instruction and not any(m.get("role") == MessageRole.SYSTEM for m in messages):
            messages.insert(0, {"role": MessageRole.SYSTEM, "content": self.system_instruction})

        max_steps = 10
        if config and "configurable" in config:
            max_steps = config["configurable"].get("max_steps", 10)
        return messages, max_steps
    
    def _parse_tool_arguments(self, tool_args: Any) -> Tuple[bool, Any]:
        """Robust parsing of JSON input parameters returned by large language models"""
        if isinstance(tool_args, str):
            try:
                return True, json.loads(tool_args)
            except Exception as e:
                logger.error(t("agent_runner.tool_arg_error", e=e, tool_args=repr(tool_args)))
                return False, None
        return True, tool_args
    
    async def _execute_tool_async(self, tool_name: str, tool_args: Any) -> str:

        if tool_name not in self.tools_map:
            observation = t("agent_runner.tool_not_found", tool_name=tool_name)
            logger.error(observation)
            return observation
        
        try:
            observation = await self.tools_map[tool_name].ainvoke(tool_args)
            return str(observation)
        except Exception as e:                        
            observation = t("agent_runner.tool_exec_error", tool_name=tool_name, error=e)
            logger.error(observation)
            return observation
        
    def _execute_tool_sync(self, tool_name: str, tool_args: Any) -> str:
        """Tool lookup and sandbox-safe invocation in synchronous contexts (including asynchronous tool bridging)"""
        if tool_name not in self.tools_map:
            observation = t("agent_runner.tool_not_found", tool_name=tool_name)
            logger.error(observation)
            return observation

        tool = self.tools_map[tool_name]
        try:
            if tool.is_async:
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                observation = loop.run_until_complete(tool.ainvoke(tool_args))
            else:
                observation = tool.invoke(tool_args)
            return str(observation)
        except Exception as e:                        
            observation = t("agent_runner.tool_exec_error", tool_name=tool_name, error=e)
            logger.error(observation)
            return observation
        
    def _handle_max_steps_error(self, messages: List[Dict[str, Any]]) -> None:
        """Unified handling of error interception exceeding the maximum inference step limit"""
        final_output = t("agent_runner.max_steps_error")
        logger.error(final_output)
        messages.append({"role": MessageRole.ASSISTANT, "content": final_output})

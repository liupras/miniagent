#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-17
# @description: AgentRunner — wraps a LangChain agent (with multi-turn memory)

"""
AgentRunner lifecycle
─────────────────────
One AgentRunner is created per agent_id by AgentFactory (see agent_factory.py).
It is immutable after construction; tools and prompts are fixed at build time.
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Dict, List, Optional

from langchain_core.runnables import Runnable
from loguru import logger

from app.infra.db.database import LLM
from app.runtime.agent.react_agent import ToolReActAgent
from app.runtime.conversation.service_conversation import ConversationService
from app.runtime.types import MessageRole, LangChainMessageRole
from app.runtime.llm.client import LLMClient
from app.runtime.llm.agent_client import AgentLLM
from app.infra.db.database import Agent as AgentORM

def _extract_content(msg: Any) -> str:
    """Adaptive message text extraction: Supports both pure dict and LangChain BaseMessage objects."""
    if isinstance(msg, dict):
        return msg.get("content", "")
    return getattr(msg, "content", "")

def _extract_tool_calls(msg: Any) -> Optional[List[Dict[str, Any]]]:
    """Adaptive extraction of standardized tool call information"""
    if isinstance(msg, dict):
        if "tool_calls" in msg:
            return [{"name": tc.get("function", {}).get("name")} for tc in msg["tool_calls"]]
        return None
    # Future-compatible LangGraph message objects
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        return [{"name": tc.get("name")} for tc in tool_calls]
    return None

def _ensure_dict_messages(messages: List[Any]) -> List[Dict[str, Any]]:
    """The list containing LangChain message objects will be cleaned and standardized into a pure dictionary format required by the self-developed Agent."""
    cleaned = []
    for m in messages:
        if isinstance(m, dict):
            cleaned.append(m.copy())
        else:
            if m.type == LangChainMessageRole.HUMAN:
                cleaned.append({"role": MessageRole.USER, "content": m.content})
            elif m.type == LangChainMessageRole.AI:
                msg_dict = {"role": MessageRole.ASSISTANT, "content": m.content}
                if hasattr(m, "tool_calls") and m.tool_calls:
                    msg_dict["tool_calls"] = [
                        {"function": {"name": tc.get("name"), "arguments": tc.get("args")}}
                        for tc in m.tool_calls
                    ]
                cleaned.append(msg_dict)
            elif m.type == LangChainMessageRole.SYSTEM:
                cleaned.append({"role": MessageRole.SYSTEM, "content": m.content})
            elif m.type == LangChainMessageRole.TOOL:
                cleaned.append({
                    "role": MessageRole.TOOL, 
                    "content": m.content, 
                    "name": getattr(m, "name", ""),
                    "tool_call_id": getattr(m, "tool_call_id", "")
                })
    return cleaned

class AgentRunner:
    """
    Thin wrapper around a compiled LangChain agent.
    """

    def __init__(
        self,
        agent_id: int,
        agent_name: str,
        agent:Runnable,
        system_prompt: str,
        chat_service: ConversationService,
        llm_config:LLM,
    ):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self._agent = agent
        self._system_prompt = system_prompt
        self._conversation_service = chat_service
        self._llm_config = llm_config

    # ── Convenience properties (read through llm_config so values stay current) ──

    @property
    def _max_tokens(self) -> int:
        return self._llm_config.max_tokens or 2000

    @property
    def _model_name(self) -> str:
        return self._llm_config.model_name

    @property
    def _temperature(self) -> float:
        return self._llm_config.temperature if self._llm_config.temperature is not None else 0.7

    # ──────────────────────────────────────────────────────────────────────
    # Public interface
    # ──────────────────────────────────────────────────────────────────────

    async def invoke(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
        *,
        user_id: Optional[str] = None,
        session_id: Optional[int] = None,
    ) -> str:
        """
        Run the agent to completion and return the final answer as a string.

        When user_id and session_id are both provided, conversation history is
        automatically loaded from and saved to the database.

        Args:
            query       The user's current message.
            history     Optional explicit prior conversation turns (role/content
                        dicts).  Overrides DB history when both are present.
            user_id     User identifier for persistent memory (optional).
            session_id  Session identifier for persistent memory (optional).

        Returns:
            The agent's final text response.
        """
        use_db = bool(user_id)

        # ── Persist user message ───────────────────────────────────────────
        if use_db:
            await self._conversation_service.save_message(
                user_id=user_id,
                agent_id = self.agent_id,
                session_id=session_id,
                role="user",
                content=query,
            )

        messages = await self._conversation_service.build_messages(
            query=query, 
            system_prompt = self._system_prompt,
            max_tokens=self._max_tokens,
            history = history, 
            user_id = user_id, 
            session_id = session_id
        )
        logger.debug(
            f"[AgentRunner:{self.agent_name}] invoke — "
            f"{len(messages)} message(s) in context."
        )

        if hasattr(self._agent, "agent_llm"):
            messages = _ensure_dict_messages(messages)

        result = await self._agent.ainvoke({"messages": messages})

        # The final AI message is always the last element.
        latest_msg = result["messages"][-1]
        answer: str = _extract_content(latest_msg)

        # ── Persist assistant reply ────────────────────────────────────────
        if use_db:
            await self._conversation_service.save_message(
                user_id=user_id,
                agent_id=self.agent_id,
                session_id=session_id,
                role="assistant",
                content=answer,
            )

        return answer

    async def stream(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
        *,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream the agent's response token-by-token.

        Yields plain text fragments (not SSE-wrapped); callers can wrap with
        generate_stream_response() from client.py if needed.

        When user_id and session_id are both provided, the user message is
        saved before streaming starts, and the complete assistant reply is
        saved once streaming finishes.

        Args:
            query       The user's current message.
            history     Optional explicit prior conversation turns.
            user_id     User identifier for persistent memory (optional).
            session_id  Session identifier for persistent memory (optional).

        Yields:
            String tokens / chunks from the LLM.
        """
        use_db = bool(user_id and session_id)

        # ── Persist user message ───────────────────────────────────────────
        if use_db:
            await self._conversation_service.save_message(
                user_id=user_id,
                agent_id = self.agent_id,
                session_id=session_id,
                role="user",
                content=query,
            )

        messages = await self._conversation_service.build_messages(
            query=query, 
            system_prompt = self._system_prompt,
            max_tokens=self._max_tokens,
            history = history, 
            user_id = user_id, 
            session_id = session_id
        )
        logger.debug(
            f"[AgentRunner:{self.agent_name}] stream — "
            f"{len(messages)} message(s) in context."
        )

        if hasattr(self._agent, "agent_llm"):
            messages = _ensure_dict_messages(messages)

        collected_chunks: List[str] = []

        async for chunk in self._agent.astream(
            {"messages": messages},
            #stream_mode="values",
        ):
            if isinstance(chunk, dict):
                latest_message = chunk["messages"][-1]
                msg_content = _extract_content(latest_message)
                if msg_content:
                    tool_calls = _extract_tool_calls(latest_message)
                    if tool_calls:
                        content = f"[Tool call] {', '.join(tc['name'] for tc in tool_calls)}"
                        logger.debug(f"Calling tools: {content}")
                        #yield content
                        yield json.dumps({
                            "event": "tool_start", 
                            "tools": [tc['name'] for tc in tool_calls]
                        }, ensure_ascii=False)                        
                    else:
                        msg_content = _extract_content(latest_message)
                        if msg_content:
                            # Incremental differential calculation (since it is in values ​​mode, the complete current text will be obtained each time, and the content that has already been printed needs to be subtracted).
                            current_chunk = msg_content[len("".join(collected_chunks)):]
                            if current_chunk:
                                collected_chunks.append(current_chunk)
                                #yield current_chunk
                                yield json.dumps({
                                    "event": "text", 
                                    "chunk": current_chunk
                                }, ensure_ascii=False)

        # ── Persist complete assistant reply ───────────────────────────────
        if use_db and collected_chunks:
            full_reply = "".join(collected_chunks)
            await self._conversation_service.save_message(
                user_id=user_id,
                agent_id=self.agent_id,
                session_id=session_id,
                role="assistant",
                content=full_reply,
            )

# ─────────────────────────────────────────────────────────────────────────────
# Builder function (called by AgentFactory)
# ─────────────────────────────────────────────────────────────────────────────

async def build_agent_runner(
    agent_orm:AgentORM,              # Agent ORM row (with .llm eagerly loaded)
    tools: List[Any],       # List[BaseTool] from tool_builder   
    chat_service: ConversationService,
) -> AgentRunner:
    """
    Construct an AgentRunner for *agent_orm*.

    Steps
    ─────
    1. Resolve the system prompt (DB value + optional i18n suffix).
    2. Build a ChatOpenAI model pointing at the agent's LLM config.
    3. Compile a LangChain agent.
    4. Wrap in AgentRunner.

    Args:
        agent_orm       Agent ORM row; must have ``.llm`` pre-loaded.
        tools           Already-built LangChain tools list.

    Returns:
        Ready-to-use AgentRunner.
    """
    # ── 1. System prompt ───────────────────────────────────────────────────
    base_prompt: str = agent_orm.system_prompt or ""
    # Optionally append an i18n-sourced suffix (key: "agent_system_suffix").
    from app.core.prompt_loader import prompt_loader
    suffix: str = prompt_loader.get("agent_system_suffix")
    system_prompt = (base_prompt + "\n\n" + suffix).strip() if suffix else base_prompt


    # ── 2. LLM ────────────────────────────────────────────────────────────    
    llm_config = agent_orm.llm
    if llm_config is None:
        raise ValueError(
            f"Agent '{agent_orm.name}' has no LLM configured. "
            "Set llm_provider on the Agent record."
        )
    
    is_thinking_model = "qwen3" in llm_config.model_name.lower()
    is_local_ollama = (
        "localhost" in llm_config.base_url
        or "127.0.0.1" in llm_config.base_url
    )
    # Close thinking
    if is_thinking_model and is_local_ollama:
        system_prompt = "/no_think\n\n" + system_prompt     

    llm_client = LLMClient(
        base_url=llm_config.base_url,
        api_key=llm_config.api_key,
        temperature=llm_config.temperature,
    )
    
    agent_llm_client = AgentLLM(client=llm_client, model=llm_config.model_name)

    # ── 3. Compile LangChain agent ──────────────────────────────────
    agent = ToolReActAgent(
        agent_llm=agent_llm_client,
        tools=tools,
        system_instruction=system_prompt
    )

    logger.info(
        f"[AgentRunner] Built agent '{agent_orm.name}' "
        f"with {len(tools)} tool(s), LLM='{llm_config.model_name}'."
    )

    return AgentRunner(
        agent_id=agent_orm.id,
        agent_name=agent_orm.name,
        agent=agent,
        system_prompt=system_prompt,
        chat_service=chat_service,
        llm_config=llm_config,
    )

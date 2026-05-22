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

The runner exposes two methods:
    invoke(query, history)   → str          (one-shot, full response)
    stream(query, history)   → AsyncGen     (token-by-token streaming)

Multi-turn conversation (persistent memory)
───────────────────────────────────────────
When user_id + session_id are supplied, the runner will:
  1. Load recent history from the DB via AsyncChatDatabase.
  2. Merge caller-supplied history (takes precedence) with DB history so that
     stateless REST calls can still pass an explicit history list.
  3. Save the user message and the agent reply to the DB automatically.
  4. Truncate the combined context with func.truncate_messages() so the total
     token count never exceeds the LLM's max_tokens budget.

Context-window budget
─────────────────────
  budget = llm_config.max_tokens  (from the Agent → LLM row)
  A safety margin of CONTEXT_TOKEN_RESERVE is subtracted to leave room for the
  model's output.  The remainder is the maximum allowed input token count.

History format follows the LangChain/LangGraph messages convention:
    [{"role": "user"|"assistant"|"system", "content": "..."}]

System prompt resolution
────────────────────────
1. Agent.system_prompt from the DB  (mandatory)
2. PromptLoader injects i18n-aware extra guidance from the I18n table.
   The special key ``agent_system_suffix`` (if present) is appended to the
   base system prompt.  This lets admins customise the agent's behaviour from
   the admin UI without a code deploy.

"""

from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from loguru import logger

from app.repositories.async_chat import AsyncChatDatabase
from app.infra.db.database import LLM
from app.infra.llm.func import truncate_messages, estimate_messages_tokens

# How many tokens to reserve for the model's *output*.
# Input context is capped at  max_tokens - CONTEXT_TOKEN_RESERVE.
CONTEXT_TOKEN_RESERVE: int = 500

# Maximum number of historical turns fetched from the DB per request.
# Each turn = 1 user message + 1 assistant message → up to 2 * DB_HISTORY_LIMIT rows.
DB_HISTORY_LIMIT: int = 40

class AgentRunner:
    """
    Thin wrapper around a compiled LangChain agent with optional persistent
    multi-turn memory backed by AsyncChatDatabase.

    Attributes
    ──────────
    agent_id        DB primary key (int).
    agent_name      Human-readable name (for logging).
    _agent         Compiled LangChain agent.
    _system_prompt  Fully resolved system prompt string.
    _chat_db        AsyncChatDatabase instance (injected at build time).
    _max_tokens     LLM max_tokens; used for context-window budgeting.
    """

    def __init__(
        self,
        agent_id: int,
        agent_name: str,
        agent,                  # compiled LangChain agent
        system_prompt: str,
        chat_db: AsyncChatDatabase,
        llm_config:LLM,
    ):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self._agent = agent
        self._system_prompt = system_prompt
        self._chat_db = chat_db
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
        session_id: Optional[str] = None,
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
        use_db = bool(user_id and session_id)

        # ── Persist user message ───────────────────────────────────────────
        if use_db:
            await self._chat_db.save_message(
                user_id=user_id,
                session_id=session_id,
                role="user",
                content=query,
            )

        messages = await self._build_messages(query, history, user_id, session_id)
        logger.debug(
            f"[AgentRunner:{self.agent_name}] invoke — "
            f"{len(messages)} message(s) in context."
        )

        result = await self._agent.ainvoke({"messages": messages})

        # The final AI message is always the last element.
        final_msg: BaseMessage = result["messages"][-1]
        answer: str = final_msg.content

        # ── Persist assistant reply ────────────────────────────────────────
        if use_db:
            await self._chat_db.save_message(
                user_id=user_id,
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
            await self._chat_db.save_message(
                user_id=user_id,
                session_id=session_id,
                role="user",
                content=query,
            )

        messages = await self._build_messages(query, history, user_id, session_id)
        logger.debug(
            f"[AgentRunner:{self.agent_name}] stream — "
            f"{len(messages)} message(s) in context."
        )

        collected_chunks: List[str] = []

        async for chunk in self._agent.astream(
            {"messages": messages},
            stream_mode="values",
        ):
            if isinstance(chunk, dict):
                latest_message = chunk["messages"][-1]
                if latest_message.content:
                    tool_calls = getattr(latest_message, "tool_calls", None)
                    if tool_calls:
                        content = f"[Tool call] {', '.join(tc['name'] for tc in tool_calls)}"
                        print(f"Calling tools: {content}")
                        yield content
                    else:
                        collected_chunks.append(latest_message.content)
                        yield latest_message.content

        # ── Persist complete assistant reply ───────────────────────────────
        if use_db and collected_chunks:
            full_reply = "".join(collected_chunks)
            await self._chat_db.save_message(
                user_id=user_id,
                session_id=session_id,
                role="assistant",
                content=full_reply,
            )

    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────

    async def _load_db_history(
        self,
        user_id: str,
        session_id: str,
    ) -> List[Dict[str, str]]:
        """
        Fetch recent conversation turns from the database.

        get_chat_history_latest() returns rows in *descending* order
        (newest first).  We reverse them so the list is chronological
        (oldest → newest) before returning.

        Note: the current user message has already been written to the DB
        before this helper is called, so we exclude the last row (which is
        the message we just saved) to avoid duplicating it in history.
        """
        rows = await self._chat_db.get_chat_history_latest(
            user_id=user_id,
            session_id=session_id,
            limit=DB_HISTORY_LIMIT + 1,  # +1 to cover the just-saved user msg
        )
        # Drop the first row (newest = the user message we just persisted).
        rows = rows[1:]
        # Desc order.
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    async def _build_messages(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]],
        user_id: Optional[str],
        session_id: Optional[str],
    ) -> List[BaseMessage]:
        """
                Build the LangChain message list for a single turn.

        Priority rules
        ──────────────
        1. If caller passed an explicit ``history`` list, use it as-is
           (backward-compatible with stateless callers).
        2. If user_id + session_id are provided and no explicit history is
           given, load history from the database.
        3. Merge: [SystemMessage] + history + [HumanMessage(query)].
        4. Truncate to fit within the LLM context budget.

        Layout after truncation:
            SystemMessage(system_prompt)
            … history messages (oldest → newest, pruned from the middle) …
            HumanMessage(query)
        """
        # ── Resolve history source ─────────────────────────────────────────
        if history is not None:
            # Caller supplied explicit history — use it directly.
            resolved_history = history
        elif user_id and session_id:
            # Load from DB (already saved the current user msg, so skip it).
            resolved_history = await self._load_db_history(user_id, session_id)
        else:
            resolved_history = []

        # ── Build raw dict list for token budgeting ────────────────────────
        system_dict = {"role": "system", "content": self._system_prompt}
        query_dict = {"role": "user", "content": query}

        # History comes in reverse-chronological
        raw_msgs = (
            [system_dict]
            + [query_dict]
            + list(resolved_history)
        )

        # Leave CONTEXT_TOKEN_RESERVE tokens for the model's output.
        input_budget = max(self._max_tokens - CONTEXT_TOKEN_RESERVE, 512)
        truncated = truncate_messages(raw_msgs, input_budget)

        # ── Convert to LangChain message objects ───────────────────────────
        msgs: List[BaseMessage] = []
        for turn in truncated:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "system":
                msgs.append(SystemMessage(content=content))
            elif role == "user":
                msgs.append(HumanMessage(content=content))
            elif role == "assistant":
                msgs.append(AIMessage(content=content))
        
        total_tokens = estimate_messages_tokens(
            [{"role": t.get("role", ""), "content": t.get("content", "")} for t in truncated]
        )
        logger.debug(
            f"[AgentRunner:{self.agent_name}] context — "
            f"{len(msgs)} messages, ~{total_tokens} tokens "
            f"(budget={input_budget})."
        )
        return msgs

# ─────────────────────────────────────────────────────────────────────────────
# Builder function (called by AgentFactory)
# ─────────────────────────────────────────────────────────────────────────────

async def build_agent_runner(
    agent_orm,              # Agent ORM row (with .llm eagerly loaded)
    tools: List[Any],       # List[BaseTool] from tool_builder
    prompt_loader,          # PromptLoader instance
    chat_db: AsyncChatDatabase,
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
        prompt_loader   PromptLoader for the active system language.

    Returns:
        Ready-to-use AgentRunner.
    """
    # ── 1. System prompt ───────────────────────────────────────────────────
    base_prompt: str = agent_orm.system_prompt or ""
    # Optionally append an i18n-sourced suffix (key: "agent_system_suffix").
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

    chat_model = ChatOpenAI(
        model=llm_config.model_name,
        openai_api_base=llm_config.base_url,
        openai_api_key=llm_config.api_key or "none",
        temperature=llm_config.temperature if llm_config.temperature is not None else 0.7,
        max_tokens=llm_config.max_tokens or 2000,
        streaming=True,         # enables token streaming via .astream()        
    )

    # ── 3. Compile LangChain agent ──────────────────────────────────
    agent = create_agent(
        model=chat_model,
        tools=tools,
        # prompt= is intentionally omitted here; we inject the SystemMessage
        # manually inside AgentRunner._build_messages() to preserve full
        # control over history ordering and i18n suffix concatenation.
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
        chat_db=chat_db,
        llm_config=llm_config,
    )

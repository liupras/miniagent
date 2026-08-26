#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-01-19
# @description: Agent LLM client

import json
from typing import List, Dict, Any, Optional

from .client import LLMClient
from app.runtime.types import MessageRole
from app.runtime.conversation.service_conversation import calculate_input_budget
from app.core.logger_config import get_logger
from app.utils.tokens import TokenCounter, sanitize_chat_messages

logger = get_logger(__name__)

class AgentLLM:
    def __init__(
        self, 
        client:LLMClient, 
        model: str,            
        tool_prompt_template: str=None,
        context_window_tokens: Optional[int] = None,
        max_output_tokens: Optional[int] = None,
        token_counter: Optional[TokenCounter] = None,
    ):
        self.client = client
        self.model = model
        self.context_window_tokens = context_window_tokens
        self.max_output_tokens = (
            max_output_tokens
            if max_output_tokens is not None
            else getattr(client, "max_output_tokens", None)
        )
        self.token_counter = token_counter or TokenCounter(model=model)
        self._tool_prompt_template = (
            tool_prompt_template
            or self._default_tool_prompt()
        )
      

    def chat(self, messages: List[Dict], tool_schema=None) -> Dict[str, Any]:
        """
        The interface adapted for SQLAgent:
        Returns:
        - tool_call
        - or content
        """

        full_messages = self._build_messages(
            messages,
            tool_schema,
        )           

        resp = self.client.chat(
            model=self.model,
            messages=full_messages,
            stream=False
        )

        return self._build_response(resp)
    
    async def achat(
        self,
        messages,
        tool_schema=None,
    ):

        full_messages = self._build_messages(
            messages,
            tool_schema,
        )

        resp = await self.client.achat(
            model=self.model,
            messages=full_messages,            
        )

        return self._build_response(resp)
    
    def _build_messages(
        self,
        messages: List[Dict],
        tool_schema=None,
    ) -> List[Dict]:

        full_messages = messages.copy()

        if tool_schema and not self._has_tool_prompt(full_messages):
            tool_prompt = self._tool_prompt_template.format(
                tool_schema=json.dumps(
                    tool_schema,
                    indent=2,
                    ensure_ascii=False,
                )
            )
            full_messages.insert(
                0,
                {
                    "role": MessageRole.SYSTEM,
                    "content": tool_prompt,
                    "_tool_prompt": True,
                },
            )

        provider_messages = sanitize_chat_messages(full_messages)
        return self._fit_messages_to_context(provider_messages)

    def _fit_messages_to_context(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Trim complete conversation turns before every model request."""
        if self.context_window_tokens is None or self.max_output_tokens is None:
            return messages

        input_budget = calculate_input_budget(
            context_window_tokens=self.context_window_tokens,
            max_output_tokens=self.max_output_tokens,
        )
        original_tokens = self._count_messages(messages, budget=input_budget)
        if original_tokens <= input_budget:
            return messages

        system_messages: List[Dict[str, Any]] = []
        body_start = 0
        for message in messages:
            if message.get("role") != MessageRole.SYSTEM:
                break
            system_messages.append(message)
            body_start += 1

        system_tokens = self._count_messages(system_messages)
        if system_tokens >= input_budget:
            raise ValueError(
                "System prompts and tool schemas exceed the available input token budget"
            )

        turns = self._split_turns(messages[body_start:])
        if not turns:
            return system_messages

        remaining = input_budget - system_tokens
        latest_turn = turns[-1]
        compacted_latest = self._compact_latest_turn(latest_turn, remaining)
        selected_turns: List[List[Dict[str, Any]]] = [compacted_latest]
        remaining -= self._count_messages(compacted_latest)

        for turn in reversed(turns[:-1]):
            turn_tokens = self._count_messages(turn)
            if turn_tokens > remaining:
                break
            selected_turns.append(turn)
            remaining -= turn_tokens

        selected_turns.reverse()
        trimmed = system_messages + [
            message
            for turn in selected_turns
            for message in turn
        ]
        trimmed_tokens = self._count_messages(trimmed, budget=input_budget)
        if trimmed_tokens > input_budget:
            raise ValueError(
                "Unable to fit the latest ReAct turn into the available input token budget"
            )
        logger.debug(
            "[AgentLLM] ReAct context trimmed from ~{} to ~{} tokens "
            "(input_budget={}, messages={}->{}).",
            original_tokens,
            trimmed_tokens,
            input_budget,
            len(messages),
            len(trimmed),
        )
        return trimmed

    def _count_messages(
        self,
        messages: List[Dict[str, Any]],
        budget: Optional[int] = None,
    ) -> int:
        return self.token_counter.count_messages(messages, budget=budget)

    @staticmethod
    def _split_turns(messages: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        turns: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []
        for message in messages:
            if message.get("role") == MessageRole.USER and current:
                turns.append(current)
                current = []
            current.append(message)
        if current:
            turns.append(current)
        return turns

    def _compact_latest_turn(
        self,
        turn: List[Dict[str, Any]],
        budget: int,
    ) -> List[Dict[str, Any]]:
        if self._count_messages(turn) <= budget:
            return turn

        first = turn[0]
        blocks = self._split_tool_blocks(turn[1:])

        # Keep at least the protocol metadata for the newest assistant/tool
        # exchange. Otherwise one very large user message could consume the
        # whole budget and orphan the ReAct loop from its latest observation.
        first_budget = budget
        if blocks:
            latest_skeleton_tokens = self._count_messages(
                self._empty_tool_contents(blocks[-1])
            )
            empty_first_tokens = self._count_messages(
                [{**first, "content": ""}]
            )
            if empty_first_tokens + latest_skeleton_tokens <= budget:
                first_budget -= latest_skeleton_tokens

        first_compacted = self._truncate_message_content(first, first_budget)
        first_tokens = self._count_messages([first_compacted])
        if first_tokens >= budget:
            return [first_compacted]

        selected: List[List[Dict[str, Any]]] = []
        remaining = budget - first_tokens

        for block in reversed(blocks):
            block_tokens = self._count_messages(block)
            if block_tokens <= remaining:
                selected.append(block)
                remaining -= block_tokens
                continue

            if not selected:
                compacted = self._compact_tool_block(block, remaining)
                if compacted:
                    selected.append(compacted)
            break

        selected.reverse()
        return [first_compacted] + [
            message
            for block in selected
            for message in block
        ]

    @staticmethod
    def _split_tool_blocks(messages: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        blocks: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []
        for message in messages:
            if message.get("role") == MessageRole.ASSISTANT and current:
                blocks.append(current)
                current = []
            current.append(message)
        if current:
            blocks.append(current)
        return blocks

    def _compact_tool_block(
        self,
        block: List[Dict[str, Any]],
        budget: int,
    ) -> List[Dict[str, Any]]:
        if budget <= 0:
            return []

        skeleton = self._empty_tool_contents(block)
        if self._count_messages(skeleton) > budget:
            return []

        compacted = skeleton
        marker = "\n[Content truncated to fit the model context window]"
        for index, message in enumerate(block):
            if message.get("role") != MessageRole.TOOL:
                continue

            content = message.get("content", "")
            if not isinstance(content, str):
                candidate = compacted.copy()
                candidate[index] = message
                if self._count_messages(candidate) <= budget:
                    compacted = candidate
                continue

            candidate = compacted.copy()
            candidate[index] = message
            if self._count_messages(candidate) <= budget:
                compacted = candidate
                continue

            low, high = 0, len(content)
            best = compacted[index]
            while low <= high:
                middle = (low + high) // 2
                updated = {
                    **message,
                    "content": content[:middle] + marker,
                }
                candidate = compacted.copy()
                candidate[index] = updated
                if self._count_messages(candidate) <= budget:
                    best = updated
                    low = middle + 1
                else:
                    high = middle - 1
            compacted[index] = best
        return compacted

    @staticmethod
    def _empty_tool_contents(
        block: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return [
            {**message, "content": ""}
            if message.get("role") == MessageRole.TOOL
            else message
            for message in block
        ]

    def _truncate_message_content(
        self,
        message: Dict[str, Any],
        budget: int,
    ) -> Dict[str, Any]:
        content = message.get("content", "")
        if not isinstance(content, str) or self._count_messages([message]) <= budget:
            return message

        marker = "\n[Content truncated to fit the model context window]"
        empty_message = {**message, "content": ""}
        if self._count_messages([empty_message]) > budget:
            raise ValueError("Message metadata exceeds the available input token budget")

        marker_message = {**message, "content": marker}
        if self._count_messages([marker_message]) > budget:
            return empty_message

        low, high = 0, len(content)
        best = marker
        while low <= high:
            middle = (low + high) // 2
            candidate = {**message, "content": content[:middle] + marker}
            if self._count_messages([candidate]) <= budget:
                best = candidate["content"]
                low = middle + 1
            else:
                high = middle - 1
        return {**message, "content": best}
    
    def _build_response(self,resp):

        content = resp.content.strip()

        tool_calls = self._parse_tool_call(content)

        if tool_calls:
            return {
                "role": MessageRole.ASSISTANT,
                "content": content,
                "tool_calls": tool_calls,
            }

        return {
            "role": MessageRole.ASSISTANT,
            "content": content,
        }
    
    @staticmethod
    def _has_tool_prompt(messages: List[Dict])->bool:
        return any(
            m.get("_tool_prompt") is True
            for m in messages
        )


    def _default_tool_prompt(self) -> str:
        """Build a prompt; this is key."""
        return """
You can use the following tool (must be called in JSON format):

{tool_schema}

When calling the tool, the output must strictly match:
{{
    "tool_calls": [
        {{
            "id": "call_unique_id",
            "type": "function",
            "function": {{
                "name": "tool_name",
                "arguments": {{...}}
            }}
        }}
    ]
}}

Note:
- Only output JSON, do not interpret it
- Do not add markdown
- Do not output any extra content
"""

    def _parse_tool_call(self, text: str):
        """JSON parsing tool call"""
        if not text:
            return None
        
        clean_text = text.strip()

        if "```" in clean_text:
            import re
            # Extract the longest segment enclosed in ```
            blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', clean_text)
            if blocks:
                # Try parsing the extracted block content first.
                for block in blocks:
                    try:
                        data = json.loads(block.strip())
                        if "tool_calls" in data:
                            return data["tool_calls"]
                    except:
                        continue
    
        # fallback solution: Use regular expressions to match the outermost {}
        # This applies to situations where parsing fails due to missing or missing ```, 
        # or where the JSON contains natural language before or after it.
        try:
            import re
            match = re.search(r'(\{[\s\S]*\})', clean_text)
            if match:
                json_str = match.group(1)
                data = json.loads(json_str)
                if "tool_calls" in data:
                    return data["tool_calls"]
        except Exception:
            pass

        return None

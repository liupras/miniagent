#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-01-19
# @description: Agent LLM client

import json
from typing import List, Dict, Any

from .client import LLMClient
from app.runtime.types import MessageRole

class AgentLLM:
    def __init__(
        self, 
        client:LLMClient, 
        model: str,            
        tool_prompt_template: str=None
    ):
        self.client = client
        self.model = model
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

        if not tool_schema:
            return full_messages

        if self._has_tool_prompt(full_messages):
            return full_messages

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

        return full_messages
    
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
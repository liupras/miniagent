#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-07
# @description: Data Contract for Agent

from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class AgentRequest(BaseModel):
    agent_id: Optional[int] = Field(default=1, description="The Agent's unique ID (either the agent_name or the agent's unique ID)")
    agent_name: Optional[str] = Field(default="general_assistant", description="The name of the agent (either the agent_id or the agent name)")
    query: str = Field(..., description="User-input test questions", examples=["你好，请问你能帮我做什么？"])
    history: Optional[List[Dict[str, str]]] = Field(
        default=[], 
        description="Explicitly passed historical dialogue context, in the format: [{'role': 'user', 'content': 'hi'}]"
    )
    user_id: Optional[str] = Field(default=2, description="User ID used for persistent memory (optional)")
    session_id: Optional[int] = Field(default=1, description="Session ID used for persistent memory (optional)")

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-29
# @description: Data Contract for Agent

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class LLMBrief(BaseModel):
    id: int
    name: str
 
    model_config = {"from_attributes": True}
 
 
class UserBrief(BaseModel):
    id: int
    username: str
 
    model_config = {"from_attributes": True}

class AgentBase(BaseModel):
    name: str = Field(..., max_length=100, description="Agent name (unique)")
    description: Optional[str] = Field(None, description="Agent description")
    system_prompt: str = Field(..., description="System prompt")
    llm_id: Optional[int] = Field(None, description="Bound LLM ID")
    is_active: bool = Field(True, description="Whether the agent is active")


class AgentCreate(AgentBase):
    pass

class AgentUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    llm_id: Optional[int] = None
    is_active: Optional[bool] = None

class AgentOut(AgentBase):
    id: int
    created_at: datetime
    updated_at: datetime
    llm: Optional[LLMBrief] = None
    users: List[UserBrief] = []

    model_config = {"from_attributes": True}


class AgentListParams(BaseModel):
    """Query parameters for the paginated agent list."""
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    name: Optional[str] = None
    llm_id: Optional[int] = None
    user_id: Optional[int] = None
    is_active: Optional[bool] = None

class AgentUserUpdate(BaseModel):
    user_ids: list[int]

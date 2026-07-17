#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-30
# @description: User Pydantic Schemas

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

# ── Output models ──────────────────────────────────────────────────────────

class UserOptionItem(BaseModel):
    """Lightweight projection for dropdown selectors (e.g. Agent form)."""
    id: int
    username: str
    nickname: Optional[str] = None

    model_config = {"from_attributes": True}


class RoleBrief(BaseModel):
    code: str

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: int
    username: str
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    roles: List[str] = Field(default_factory=list, description="Role codes")
    permissions: List[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ── Query params ───────────────────────────────────────────────────────────

class UserListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    username: Optional[str] = None          # fuzzy
    is_active: Optional[bool] = None
    keyword: Optional[str] = None
    role_id: Optional[int] = None


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6, max_length=128)
    nickname: Optional[str] = Field(None, max_length=100)
    avatar: Optional[str] = Field(None, max_length=500)
    is_active: bool = True
    role_ids: List[int] = Field(default_factory=list)


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    nickname: Optional[str] = Field(None, max_length=100)
    avatar: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None


class UserRoleUpdate(BaseModel):
    role_ids: List[int] = Field(default_factory=list)


class UserPasswordReset(BaseModel):
    password: str = Field(..., min_length=6, max_length=128)

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-17
# @description: Schemas used by the role and menu administration APIs.

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RoleCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    is_super: bool = False
    menu_ids: list[int] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    code: str | None = Field(None, min_length=2, max_length=50, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    is_super: bool | None = None


class RoleMenuUpdate(BaseModel):
    menu_ids: list[int] = Field(default_factory=list)


class RoleOut(BaseModel):
    id: int
    code: str
    name: str
    description: str | None = None
    is_super: bool
    menu_ids: list[int] = Field(default_factory=list)
    user_count: int = 0


class RoleOption(BaseModel):
    id: int
    code: str
    name: str
    is_super: bool

    model_config = {"from_attributes": True}


MenuType = Literal["menu", "button"]


class MenuCreate(BaseModel):
    parent_id: int | None = None
    name: str = Field(..., min_length=1, max_length=100)
    title_key: str = Field(..., min_length=1, max_length=100)
    path: str | None = Field(None, max_length=200)
    component: str | None = Field(None, max_length=200)
    icon: str | None = Field(None, max_length=100)
    sort_order: int = 0
    menu_type: MenuType = "menu"
    description: str | None = None
    is_visible: bool = True
    is_active: bool = True


class MenuUpdate(BaseModel):
    parent_id: int | None = None
    name: str | None = Field(None, min_length=1, max_length=100)
    title_key: str | None = Field(None, min_length=1, max_length=100)
    path: str | None = Field(None, max_length=200)
    component: str | None = Field(None, max_length=200)
    icon: str | None = Field(None, max_length=100)
    sort_order: int | None = None
    menu_type: MenuType | None = None
    description: str | None = None
    is_visible: bool | None = None
    is_active: bool | None = None


class MenuOut(BaseModel):
    id: int
    parent_id: int | None = None
    name: str
    title_key: str
    path: str | None = None
    component: str | None = None
    icon: str | None = None
    sort_order: int
    menu_type: MenuType
    description: str | None = None
    is_visible: bool
    is_active: bool
    created_at: datetime
    children: list["MenuOut"] = Field(default_factory=list)

    model_config = {"from_attributes": True}

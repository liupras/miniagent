#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-23
# @description: Route model definitions for frontend route management

from typing import Optional
from pydantic import BaseModel, ConfigDict

class RouteMeta(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    title: str
    icon: Optional[str] = None
    rank: Optional[int] = None
    roles: Optional[list[str]] = None
    auths: Optional[list[str]] = None

class RouteItem(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    path: str
    name: Optional[str] = None
    component: Optional[str] = None
    meta: RouteMeta
    children: Optional[list["RouteItem"]] = None

RouteItem.model_rebuild()
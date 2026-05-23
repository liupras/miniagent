#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-23
# @description: Route model definitions for frontend route management

from typing import Optional
from pydantic import BaseModel

class RouteMeta(BaseModel):
    title: str
    icon: Optional[str] = None
    rank: Optional[int] = None
    roles: Optional[list[str]] = None
    auths: Optional[list[str]] = None

class RouteItem(BaseModel):
    path: str
    name: Optional[str] = None
    component: Optional[str] = None
    meta: RouteMeta
    children: Optional[list["RouteItem"]] = None

RouteItem.model_rebuild()
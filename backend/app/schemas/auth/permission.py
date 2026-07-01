#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-01
# @description: Model definitions for permission management

from pydantic import BaseModel

class CacheStatsResponse(BaseModel):
    backend:         str
    max_size:        int
    current_size:    int
    hits:            int
    misses:          int
    hit_rate:        str
    ttl_expirations: int


class RefreshResponse(BaseModel):
    user_id:     int
    permissions: list[str]
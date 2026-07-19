#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-19
# @description: Login Log schemas

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class LoginLogOut(BaseModel):
    id: int
    request_id: str
    event_type: str
    user_id: Optional[int] = None
    username: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    success: bool
    failure_reason: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

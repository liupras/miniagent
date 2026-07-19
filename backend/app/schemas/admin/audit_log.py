#!/usr/bin/python
# -*- coding:utf-8 -*-

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: int
    request_id: str
    user_id: Optional[int] = None
    username: Optional[str] = None
    ip_address: Optional[str] = None
    target_type: str
    target_id: str
    action: str
    before_value: Optional[Any] = None
    after_value: Optional[Any] = None
    description: Optional[str] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}

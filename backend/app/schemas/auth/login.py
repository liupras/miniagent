#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-29
# @description: Model definitions for auth

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List


class LoginRequest(BaseModel):
    """Login Request Body Model"""
    username: str = Field(..., min_length=3, max_length=50, description="user name")
    password: str = Field(..., min_length=1, max_length=128, description="password")


class PasswordPolicyResponse(BaseModel):
    min_length: int
    require_upper: bool
    require_lower: bool
    require_digit: bool
    require_special: bool


class LoginData(BaseModel):
    avatar: Optional[str] = None
    username: Optional[str] = None
    nickname: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)
    accessToken: str
    refreshToken: str
    expires: str       # format: "YYYY/MM/DD HH:MM:SS"


class LoginResponse(BaseModel):
    success: bool
    data: Optional[LoginData] = None
    error_code: Optional[str] = None
    message: Optional[str] = None
    locked_until: Optional[datetime] = None


class RefreshTokenRequest(BaseModel):
    refreshToken: str

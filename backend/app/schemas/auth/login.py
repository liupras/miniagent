#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-29
# @description: Model definitions for auth

from pydantic import BaseModel, Field
from typing import Optional, List


class LoginRequest(BaseModel):
    """Login Request Body Model"""
    username: str = Field(..., min_length=3, max_length=50, description="user name")
    password: str = Field(..., min_length=6, description="password")


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


class RefreshTokenRequest(BaseModel):
    refreshToken: str

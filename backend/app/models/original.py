#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-01-26
# @description: Model definitions for the application

from pydantic import BaseModel, Field
from typing import Optional, Dict, List

class LoginRequest(BaseModel):
    """Login Request Body Model"""
    user_id: str = Field(..., min_length=3, max_length=50, description="user id")
    password: str = Field(..., min_length=6, description="password")

class LoginData(BaseModel):
    avatar: str
    username: str      # = user_id value
    nickname: str
    roles: List[str]
    permissions: List[str]
    accessToken: str
    refreshToken: str
    expires: str       # format: "YYYY/MM/DD HH:MM:SS"

class LoginResponse(BaseModel):
    success: bool
    data: Optional[LoginData] = None

class SimpleChatRequest(BaseModel):
    """Chat Request (Simplified Version)"""   
    session_id: str = Field(default="default", description="Session ID, used to associate context.")
    message: str = Field(..., min_length=1, max_length=2000, description="User Messages")

class SimpleChatResponse(BaseModel):
    """Chat Response (Simplified Version)"""
    code: int = Field(default=0, description="Status code, 0 indicates success")
    msg: str = Field(default="success", description="message")
    data: Optional[Dict] = Field(default=None, description="response data")

class ChatRequest(BaseModel):
    """Chatting Request Body Model"""    
    session_id: str = Field(default="default", description="Session ID, used to associate context.")    
    messages: List[Dict[str, str]] = Field(
        ..., 
        description="Chat message list, format example: [{\"role\": \"user\", \"content\": \"Hello\"}]"
    )
    temperature: Optional[float] = Field(
        default=0.7,  # Default to the temperature specified in the configuration file
        ge=0.0, le=1.0, 
        description="Sampling temperature, range 0-1, default value is used if empty."
    )
    stream: bool = Field(default=False, description="Whether to use streaming response, the default is false.")

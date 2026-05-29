#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-01-24
# @description: OpenAI API Compatible Models

from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any, Literal
from app.core.config import settings

class Message(BaseModel):
    """OpenAI format message"""
    role: Literal["system", "user", "assistant", "function"]
    content: str
    name: Optional[str] = None
    function_call: Optional[Dict[str, Any]] = None


class OpenAIChatRequest(BaseModel):
    """OpenAI Chat Completions API compatible request model"""
    model: str = Field(
        default=settings.ai_model.model_name,
        description="ID of the model to use"
    )
    messages: List[Message] = Field(
        ...,
        description="A list of messages comprising the conversation so far"
    )
    temperature: Optional[float] = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="What sampling temperature to use, between 0 and 2"
    )
    top_p: Optional[float] = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="An alternative to sampling with temperature"
    )
    n: Optional[int] = Field(
        default=1,
        ge=1,
        description="How many chat completion choices to generate"
    )
    stream: Optional[bool] = Field(
        default=False,
        description="If set, partial message deltas will be sent"
    )
    stop: Optional[List[str]] = Field(
        default=None,
        description="Up to 4 sequences where the API will stop generating further tokens"
    )
    max_tokens: Optional[int] = Field(
        default=None,
        description="The maximum number of tokens to generate"
    )
    presence_penalty: Optional[float] = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Number between -2.0 and 2.0"
    )
    frequency_penalty: Optional[float] = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Number between -2.0 and 2.0"
    )
    logit_bias: Optional[Dict[str, float]] = Field(
        default=None,
        description="Modify the likelihood of specified tokens"
    )
    user: Optional[str] = Field(
        default=None,
        description="A unique identifier representing your end-user"
    )


class ChatCompletionMessage(BaseModel):
    """OpenAI response message"""
    role: str
    content: str


class ChatCompletionChoice(BaseModel):
    """OpenAI response choice"""
    index: int
    message: ChatCompletionMessage
    finish_reason: Optional[str] = "stop"


class Usage(BaseModel):
    """OpenAI usage statistics"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class OpenAIChatResponse(BaseModel):
    """OpenAI Chat Completions API compatible response model"""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: Optional[Usage] = None


class StreamChoice(BaseModel):
    """OpenAI streaming response choice"""
    index: int
    delta: Dict[str, Any]
    finish_reason: Optional[str] = None


class OpenAIChatStreamResponse(BaseModel):
    """OpenAI Chat Completions API streaming response model"""
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[StreamChoice]
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-01-19
# @description: LLM Models

from typing import Any, Dict, List, Optional

class LLMClientError(Exception):
    """LLM client custom exceptions"""
    pass

class LLMResponse:
    """LLM response wrapper class"""
    
    def __init__(
        self,
        content: str,
        thinking: Optional[str] = None,
        model: Optional[str] = None,
        usage: Optional[Dict] = None,

        tool_calls: Optional[List] = None,
        images: Optional[List] = None,
        audio: Optional[List] = None,
        videos: Optional[List] = None,

        raw_response: Any = None,
    ):
        """
        Initialize LLM response
        """
        self.content = content
        self.thinking = thinking
        self.model = model
        self.usage = usage or {}

        # multimodal extensions
        self.tool_calls = tool_calls or []
        self.images = images or []
        self.audio = audio or []
        self.videos = videos or []

        self.raw_response = raw_response
    
    def __str__(self) -> str:
        """String representation (only the main content is returned)"""
        return self.content
    
    def __repr__(self) -> str:
        """Detailed description"""
        return f"LLMResponse(content_len={len(self.content)}, has_thinking={self.thinking is not None})"
    
    def get_full_response(self) -> str:
        """Get the complete response (including thinking)."""
        if self.thinking:
            return f"[Thinking]\n{self.thinking}\n\n[Response]\n{self.content}"
        return self.content
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-11
# @description: Models

from enum import Enum

class MessageRole(str, Enum):
    """
    A unified Agent message role enumeration
    Also inherits from str, allowing it to be directly serialized or compared as a string.
    """
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

class LangChainMessageRole(str, Enum):
    """
    Enumerate the corresponding mapping relationships for message types (m.type) unique to LangChain.
    """
    SYSTEM = "system"
    HUMAN = "human"
    AI = "ai"
    TOOL = "tool"
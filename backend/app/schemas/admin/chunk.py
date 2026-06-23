#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-23
# @description: Data Contract for Chunk

from datetime import datetime
from typing import List
from pydantic import BaseModel, ConfigDict


class ChunkRead(BaseModel):
    """Small chunk"""
    id: int
    parent_id: int
    chunk_index: int
    text: str
    char_count: int
    token_count: int
    hash_value: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ParentChunkRead(BaseModel):
    """Big chunk"""
    id: int
    doc_id: int
    chunk_index: int
    text: str
    char_count: int
    token_count: int
    hash_value: str
    created_at: datetime
    chunks: List[ChunkRead] = []

    model_config = ConfigDict(from_attributes=True)


class DocumentChunksOut(BaseModel):
    """Document chunk query results (paged by parent_chunk)"""
    doc_id: int
    total_parent_chunks: int
    total_chunks: int
    page: int
    page_size: int
    parent_chunks: List[ParentChunkRead]
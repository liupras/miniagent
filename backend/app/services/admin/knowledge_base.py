#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-06-13
# @description: KnowledgeBase Service Layer – Business logic

from typing import Any, List, Tuple, Optional

from app.schemas.admin.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseRead,
    KnowledgeBaseUpdate,
    KnowledgeBaseOption,
    KnowledgeBaseStats
)
from app.schemas.common import NotFoundError

class KBNotFoundError(NotFoundError):
    def __init__(self, entity_id: Any):
        super().__init__("KB", entity_id)
        
class KnowledgeBaseService:
    def __init__(self, container):
        from app.core.service_container import ServiceContainer
        if not isinstance(container, ServiceContainer):
            raise TypeError(f"Expected ServiceContainer, got {type(container)}")
        
        self.db = container.kb_db
        self._retrieval_service = container.retrieval_service

    async def list_kbs(
        self,
        page: int = 1,
        page_size: int = 20,
        name_filter: str | None = None,
        domain_id: int | None = None,
        is_active: bool | None = None
    ) -> Tuple[int, List[KnowledgeBaseRead]]:
        """List knowledge bases with pagination and filters."""
        total, items = await self.db.list_kbs(
            page=page,
            page_size=page_size,
            name_filter=name_filter,
            domain_id=domain_id,
            is_active=is_active
        )
        return total, [KnowledgeBaseRead.model_validate(item) for item in items]
    
    async def kb_exists(self, kb_id: int) -> bool:
        result = await self.db.kb_exists(kb_id)
        if not result:
            raise KBNotFoundError(kb_id)
        return result
    

    async def get_kb(self, kb_id: int) -> Optional[KnowledgeBaseRead]:
        """Get a single knowledge base by ID."""
        kb = await self.db.get_kb(kb_id)
        if kb is None:
            raise KBNotFoundError(kb_id)
        return KnowledgeBaseRead.model_validate(kb)

    async def create_kb(self, payload: KnowledgeBaseCreate) -> KnowledgeBaseRead:
        """Create a new knowledge base."""
        data = payload.model_dump()
        kb = await self.db.create_kb(data)
        return KnowledgeBaseRead.model_validate(kb)

    async def update_kb(self, kb_id: int, payload: KnowledgeBaseUpdate) -> Optional[KnowledgeBaseRead]:
        """Update a knowledge base."""
        data = payload.model_dump(exclude_unset=True)
        kb = await self.db.update_kb(kb_id, data)
        if kb is None:
            raise KBNotFoundError(kb_id)
        if not self._retrieval_service:
            self._retrieval_service.invalidate(kb_id=kb_id)
        return KnowledgeBaseRead.model_validate(kb)

    async def delete_kb(self, kb_id: int) -> bool:
        """Delete a knowledge base."""
        res = await self.db.delete_kb(kb_id)
        if not res:
            raise KBNotFoundError(kb_id)
        if not self._retrieval_service:
            self._retrieval_service.invalidate(kb_id=kb_id)
        return res

    async def get_kb_options(self) -> List[KnowledgeBaseOption]:
        """Get knowledge base options for dropdown selection."""
        options = await self.db.get_kb_options()
        return [KnowledgeBaseOption.model_validate(option) for option in options]

    async def toggle_kb_active(self, kb_id: int) -> bool:
        """Toggle the active status of a knowledge base."""
        res =  await self.db.toggle_kb_active(kb_id)
        if not res:
            raise KBNotFoundError(kb_id)
        if not self._retrieval_service:
            self._retrieval_service.invalidate(kb_id=kb_id)
        return res

    async def get_kb_stats(self, kb_id: int) -> KnowledgeBaseStats:
        """Get statistics for a knowledge base."""
        stats = await self.db.get_kb_stats(kb_id)
        if not stats:
            raise KBNotFoundError(kb_id)
        return KnowledgeBaseStats.model_validate(stats)
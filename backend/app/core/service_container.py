#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-01
# @description: Application-level service container, Implement Dependency Injection.

from typing import Dict
from loguru import logger
from app.core.config import settings
from app.core.security import JWTAuth
from app.services.kb import BM25Manager, VectorStoreManager
from app.services.kb.service_document import KBDocumentService
from app.services.kb.service_retrieval import KBRetrievalService
from app.repositories import (
    AsyncChunkDatabase,
    AsyncDocumentDatabase,
    AsyncKnowledgeBaseDatabase,
    AsyncParentChunkDatabase,
    AsyncChatDatabase,
    AsyncUserDatabase,
    AsyncEmbeddingDatabase,
    AsyncDomainDatabase,
    AsyncRouterConfigDatabase,
    AsyncAgentDatabase,
    AsyncAgentToolRelationDatabase,
    AsyncToolDatabase,
    AsyncI18nDatabase,
    AsyncSystemSettingDatabase,
    AsyncLLMDatabase,
    AsyncMenuDatabase,
    AsyncAgentUserRelationDatabase,
    AsyncAgentUserRelationDatabase,
)

from app.services.sql_agent import DuckDBManager

from app.core.security.auth_permission import AuthPermission

from app.services.kb.domain_registry import DomainRegistry
from app.services.kb.smart_router import SmartRouter,RouterConfig
from app.services.kb.service_smart_router import KBSmartRouterService
from app.services.auth.route_service import RouteService
from app.runtime.agent_factory import AgentFactory
from app.services.skill.service_web_search import WebSearchService
from app.services.sql_agent import SQLAgentService
from app.storage.local import LocalStorageBackend

from app.services.admin.agent import AgentService
from app.services.admin.llm import LLMService
from app.services.admin.user import UserService
from app.services.admin.tool import ToolService
from app.services.admin.domain import DomainService
from app.services.admin.router_config import RouterConfigService

import importlib

def import_class(class_path: str):
    """Dynamically import classes based on fully qualified names."""
    module_path, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)

class ServiceContainer:
    """
    Application-level service container.

    All infrastructure objects are created once per process
    and accessed via app.state.container.
    """

    def __init__(self):

        # Create globally unique Engine and SessionFactory.
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

        db_path = settings.get_sqlite_path()
        database_url = f"sqlite+aiosqlite:///{db_path}"
        
        self.engine = create_async_engine(
            database_url,
            echo=False,
            future=True,
            # For SQLite, it's generally recommended to set pool_size=1 or use a single connection to avoid concurrency lock issues.
            # However, aiosqlite handles this better, and the default configuration is usually usable.
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False
        )

        # ── Databases ──────────────────────────────────────────────────────
        self.duckdb = DuckDBManager(settings.get_duck_db_path())

        self.user_db  = AsyncUserDatabase(self.engine, self.session_factory)
        self.chat_db  = AsyncChatDatabase(self.engine, self.session_factory)
        self.kb_db    = AsyncKnowledgeBaseDatabase(self.engine, self.session_factory)
        self.doc_db   = AsyncDocumentDatabase(self.engine, self.session_factory)
        self.pc_db    = AsyncParentChunkDatabase(self.engine, self.session_factory)
        self.chunk_db = AsyncChunkDatabase(self.engine, self.session_factory)
        self.embed_db = AsyncEmbeddingDatabase(self.engine, self.session_factory)
        self.domain_db= AsyncDomainDatabase(self.engine, self.session_factory)
        self.router_config_db = AsyncRouterConfigDatabase(self.engine, self.session_factory)
        self.agent_db = AsyncAgentDatabase(self.engine, self.session_factory)
        self.tool_db = AsyncToolDatabase(self.engine, self.session_factory)
        self.agent_tool_relation_db = AsyncAgentToolRelationDatabase(self.engine, self.session_factory)
        self.i18n_db = AsyncI18nDatabase(self.engine, self.session_factory)
        self.setting_db = AsyncSystemSettingDatabase(self.engine, self.session_factory)
        self.llm_db = AsyncLLMDatabase(self.engine, self.session_factory)
        self.menu_db = AsyncMenuDatabase(self.engine, self.session_factory)                
        self.agent_user_relation_db = AsyncAgentUserRelationDatabase(self.engine, self.session_factory)
        self.user_agent_relation_db = AsyncAgentUserRelationDatabase(self.engine, self.session_factory)

        # ── Auth ───────────────────────────────────────────────────────────
        self.jwt_auth = JWTAuth(
            secret_key  = settings.jwt_secret_key,
            algorithm   = settings.jwt_algorithm,
            expire_days = settings.jwt_access_token_expire_days,
        )

        # ── Retrieval infrastructure ───────────────────────────────────────
        self.bm25 = BM25Manager(
            storage_dir   = settings.bm25_index_path,
            max_cache_size = settings.bm25_max_cache_size,
        )
        self.vector_registry = VectorStoreRegistry(self)  
        self.domain_registry = DomainRegistry()
        self.storage = LocalStorageBackend(root_dir="./data/storage")

        self.auth: AuthPermission = AuthPermission(
            self,
            # Optionally override defaults:
            # cache_max_size=5000,
            # cache_ttl_seconds=600.0,
        )

        # ── KB service singletons ──────────────────────────────────────────
        # Both services receive the full VectorStoreRegistry so they can
        # resolve the correct VectorStoreManager per kb_id at call time.
        self.document_service = KBDocumentService(self)
        self.retrieval_service = KBRetrievalService(self)   

        self.router_factory = SmartRouterFactory(self)     
        self.smart_router_service = KBSmartRouterService(self)
        self.agent_factory = AgentFactory(self)
        self.web_search_service = WebSearchService(self)
        self.sql_agent_service=SQLAgentService(self)
        self.route_service = RouteService(self)

        self.agent_service = AgentService(self)
        self.llm_service = LLMService(db=self.llm_db)
        self.user_service = UserService(user_db=self.user_db, menu_db=self.menu_db)
        self.tool_service = ToolService(self)
        self.domain_service = DomainService(self.domain_db)
        self.router_config_service = RouterConfigService(self)

    async def start(self):
        await self.init_plugins()
        logger.info("ServiceContainer started and plugins loaded.")

    async def init_plugins(self):
        """
        Load Domain configuration from database and dynamically register plugins.
        It is recommended to call this method in the app's startup hook (such as FastAPI's startup event).
        """
        domains = await self.domain_db.get_all_domains()
        
        for domain_orm in domains:
            try:
                processor_cls = import_class(domain_orm.processor_class)
                processor_instance = processor_cls()
                plugin_cls = import_class(domain_orm.plugin_class) 
                plugin_instance = plugin_cls(processor=processor_instance)                 
                self.domain_registry.register(
                    domain=domain_orm.name,
                    plugin=plugin_instance
                )
                logger.info(f"Successfully registered plugin for domain: {domain_orm.name}")
                
            except Exception as e:
                logger.error(f"Failed to register plugin for {domain_orm.name}: {e}")

    def shutdown(self):
        """Optional: clean up resources if needed."""
        pass


# ─────────────────────────────────────────────────────────────────────────────
# VectorStoreRegistry
# ─────────────────────────────────────────────────────────────────────────────

class VectorStoreRegistry:
    """
    Lazy cache of per-KB VectorStoreManager instances.

    Each KB has its own embedding model configuration, so a separate
    VectorStoreManager is needed per KB.  This registry creates them on first
    access and caches them for reuse.

    Usage by services
    ─────────────────
    Services call registry.get(kb_id) to resolve the VectorStoreManager for
    a specific KB.  They hold a reference to the registry (not to individual
    managers) so they can serve all KBs without being re-instantiated.
    """

    def __init__(self, container:ServiceContainer):
        self._stores: Dict[int, VectorStoreManager] = {}
        self.kb_db   = container.kb_db
        self.embed_db = container.embed_db

    async def get(self, kb_id: int) -> VectorStoreManager:
        """
        Return the VectorStoreManager for *kb_id*, creating it if necessary.

        Raises ValueError if the KB does not exist.
        """
        if kb_id in self._stores:
            return self._stores[kb_id]

        kb = await self.kb_db.get_kb(kb_id)
        if not kb:
            raise ValueError(f"KB {kb_id} not found")

        store = await self._create_store_from_kb(kb)
        self._stores[kb_id] = store
        return store

    async def _create_store_from_kb(self, kb) -> VectorStoreManager:
        embed_data = await self.embed_db.get_by_name(kb.embedding_provider)
        return VectorStoreManager(
            db_path        = settings.vector_db_path,
            ollama_base_url = embed_data.base_url,
            embed_model    = embed_data.model_name,
        )

    def remove(self, kb_id: int) -> None:
        """Evict the cached VectorStoreManager for *kb_id*."""
        if kb_id in self._stores:
            del self._stores[kb_id]

class SmartRouterFactory:
    """
    Manage SmartRouter instances (one per router_config_id).
    """

    def __init__(self, container: ServiceContainer):
        self.container = container
        self._cache: Dict[str, SmartRouter] = {}

    async def get_router(self, router_config_id: str) -> SmartRouter:
        # Cache hit
        if router_config_id in self._cache:
            return self._cache[router_config_id]

        # 1. Load RouterConfig from DB
        router_config_orm = await self.container.router_config_db.get_by_id(router_config_id)
        if not router_config_orm:
            raise ValueError(f"RouterConfig {router_config_id} not found")

        # 2. Convert to dataclass
        router_config = RouterConfig(
            selection_strategy = router_config_orm.selection_strategy,
            fallback_to_all    = router_config_orm.fallback_to_all,
            max_kb_count       = router_config_orm.max_kb_count,
            extra_config       = router_config_orm.extra_config,
        )

        # 3. Building SmartRouter
        router = SmartRouter(
            kb_services  = self.container.retrieval_service,
            router_config= router_config,
            embedding_db = self.container.embed_db,
        )

        # 4. caching
        self._cache[router_config_id] = router

        return router
    
    def invalidate(self, router_config_id: str):
        self._cache.pop(router_config_id, None)

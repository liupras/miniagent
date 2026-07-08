#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-01
# @description: Application-level service container, Implement Dependency Injection.

from loguru import logger
from app.core.config import settings
from app.runtime.smart_router_factory import SmartRouterFactory
from app.runtime.vector_registry import VectorStoreRegistry
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
    AsyncPromptDatabase,
    AsyncSystemSettingDatabase,
    AsyncLLMDatabase,
    AsyncMenuDatabase,
    AsyncAgentUserRelationDatabase,
    AsyncAgentUserRelationDatabase,
    AsyncStrategyConfigDatabase,
)

from app.core.security.auth_permission import AuthPermission

from app.runtime.cache.registry import CacheRegistry

from app.services.kb.domain_registry import DomainRegistry
from app.services.kb.service_smart_router import KBSmartRouterService
from app.services.auth.route_service import RouteService
from app.runtime.agent_factory import AgentFactory
from app.services.skill.service_web_search import WebSearchService
from app.services.sql_agent.service_sql_agent import SQLAgentService

from app.services.admin.agent import AgentService
from app.services.admin.llm import LLMService
from app.services.admin.user import UserService
from app.services.admin.tool import ToolService
from app.services.admin.domain import DomainService
from app.services.admin.router_config import RouterConfigService
from app.services.admin.strategy_config import StrategyConfigService
from app.services.admin.knowledge_base import KnowledgeBaseService
from app.services.admin.embedding import EmbeddingService
from app.services.admin.system_setting import SystemSettingService
from app.services.admin.prompt import PromptService
from app.runtime.conversation.service_conversation import ConversationService

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

        db_path = settings.get_sqlite_path() / "miniagent.db"
        database_url = f"sqlite+aiosqlite:///{db_path}"
        
        self.engine = create_async_engine(
            database_url,
            echo=False,
            future=True,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False
        )

        # ── Databases ──────────────────────────────────────────────────────
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
        self.prompt_db = AsyncPromptDatabase(self.engine, self.session_factory)
        self.setting_db = AsyncSystemSettingDatabase(self.engine, self.session_factory)
        self.llm_db = AsyncLLMDatabase(self.engine, self.session_factory)
        self.menu_db = AsyncMenuDatabase(self.engine, self.session_factory)                
        self.agent_user_relation_db = AsyncAgentUserRelationDatabase(self.engine, self.session_factory)
        self.user_agent_relation_db = AsyncAgentUserRelationDatabase(self.engine, self.session_factory)
        self.strategy_config_db = AsyncStrategyConfigDatabase(self.engine, self.session_factory)

        self.auth: AuthPermission = AuthPermission(
            self,
            # Optionally override defaults:
            # cache_max_size=5000,
            # cache_ttl_seconds=600.0,
        )

        self.cache_registry = CacheRegistry()

        from app.infra.cache.store_registry import cache_registry as value_cache_registry
        self.value_cache_registry = value_cache_registry

        self.vector_registry = VectorStoreRegistry(self)
        self.router_factory = SmartRouterFactory(self)
        self.domain_registry = DomainRegistry()

        self.conversation_service = ConversationService(chat_db=self.chat_db)
        self.agent_factory = AgentFactory(self)      

        # ── Service singletons ──────────────────────────────────────────
        self.document_service = KBDocumentService(self)
        self.retrieval_service = KBRetrievalService(self)
             
        self.smart_router_service = KBSmartRouterService(self)        
        self.web_search_service = WebSearchService(self)
        self.sql_agent_service=SQLAgentService(self)
        self.route_service = RouteService(self)

        self.agent_service = AgentService(self)
        self.llm_service = LLMService(db=self.llm_db)
        self.user_service = UserService(user_db=self.user_db, menu_db=self.menu_db)
        self.tool_service = ToolService(self)
        self.domain_service = DomainService(self.domain_db)
        self.router_config_service = RouterConfigService(self)
        self.strategy_config_service = StrategyConfigService(self)
        self.kb_service = KnowledgeBaseService(self)
        self.embedding_service = EmbeddingService(db=self.embed_db)
        self.setting_service = SystemSettingService(db=self.setting_db)
        self.prompt_service = PromptService(db=self.prompt_db)
        

    async def start(self):       

        await self.init_plugins()
        logger.info("ServiceContainer started and plugins loaded.")

        from app.core.prompt_loader import PromptLoader
        import app.core.prompt_loader as LoaderModel
        LoaderModel.prompt_loader = await PromptLoader.create(
            setting_service=self.setting_service,
            prompt_service=self.prompt_service
        )        
        logger.info("prompt_loader initialized.")

        from app.core.i18n.i18n import I18n
        await I18n.create(setting_service=self.setting_service)
        logger.info("I18n initialized.")
        
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
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: MiniAgent FastAPI Main Entr,Provides a RESTful API interface for managing intelligent agents, knowledge bases, and conversations.

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import time
from typing import AsyncGenerator
from uuid import uuid4

# Important: logger_config must be imported and configured before other imports.
# This ensures that the logging system is ready before the entire application starts.
from app.core.logger_config import get_logger, setup_logger
setup_logger()
logger = get_logger(__name__)

from app.core.config import settings
from app.infra.db.initializer import init_database_on_startup

from app.core.service_container import ServiceContainer
from app.core.audit_context import (
    begin_audit_context,
    reset_audit_context,
)
from app.infra.db.audit import record_request_outcome
from app.api.exception_handlers import register_global_exception_handlers
from app.api.integrations.errors import register_integration_exception_handlers

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifecycle management"""
    # ==================== Execute at startup ====================
    logger.info("=" * 60)
    logger.info(f"🚀 {settings.app_name} v{settings.app_version}  is starting up...")
    logger.info("=" * 60)
    logger.info(f"📊 environment: {settings.environment}")
    logger.info(f"💾 SQLite: {settings.get_sqlite_path()}")
    logger.info(f"🔍 ChromaDB: {settings.get_vector_db_path()}")
    logger.info("=" * 60)
    
    # 🔥 Automatic database initialization
    try:
        init_database_on_startup(
            force_rebuild=False,  # Set to False for production environments, and to True for development environments.
            seed_data=True        # Should preset data be filled?
        )
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        logger.exception(e)

        # Decide whether to continue the startup process (you can choose to throw an exception to prevent startup).
        # raise
    
    logger.info("=" * 60)
    logger.success("✅ Application startup complete")
    logger.info("=" * 60)

    container = ServiceContainer()
    await container.start()
    app.state.container = container
    
    yield
    
    # ==================== Execute when closing ====================
    app.state.container.shutdown()
    logger.info("=" * 60)
    logger.info(f"👋 {settings.app_name} is closing...")
    logger.info("=" * 60)


# Creating FastAPI applications
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Lightweight Agent Platform - Automatic Database Initialization",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    # Keep Starlette's traceback response disabled so the registered global
    # Exception handler is authoritative in every environment. Application
    # log verbosity remains controlled by settings.debug.
    debug=False,
)
register_global_exception_handlers(app)
register_integration_exception_handlers(app)

# ==================== Middleware configuration ====================

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Log Middleware
_AUTH_LOG_EVENTS = {
    "/api/v1/login": "LOGIN",
    "/api/v1/refresh-token": "REFRESH_TOKEN",
}


async def record_unhandled_auth_attempt(request: Request) -> None:
    """Record auth calls rejected before their endpoint body can run."""
    if request.method != "POST":
        return

    event_type = _AUTH_LOG_EVENTS.get(request.url.path)
    if not event_type:
        return

    # Prefer the middleware-generated request_id so login-log DB entries
    # share the same correlation ID as the file/console logs.
    request_id = (
        getattr(request.state, "request_id", None)
        or getattr(request.state, "login_request_id", None)
        or str(uuid4())
    )
    if getattr(request.state, "login_log_recorded", False):
        return

    try:
        values = getattr(request.state, "login_log_payload", None) or {
            "request_id": request_id,
            "event_type": event_type,
            "success": False,
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
            "failure_reason": "request_validation_error",
        }
        await request.app.state.container.login_log_service.record(**values)
        request.state.login_log_recorded = True
    except Exception as exc:
        logger.exception(f"Login log fallback write failed: {exc}")


async def record_request_outcome_safely(request: Request, status_code: int) -> None:
    """Persist secondary request records without changing the response."""
    await record_unhandled_auth_attempt(request)

    try:
        route = request.scope.get("route")
        await record_request_outcome(
            request.app.state.container.audit_log_db,
            status_code=status_code,
            route_name=getattr(route, "name", None),
            path_params=dict(request.path_params),
        )
    except Exception as audit_exc:
        # Audit failures must never change the business response.
        logger.exception(f"Audit log write failed: {audit_exc}")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Record all HTTP requests and inject request_id into every log line."""
    request_id = str(uuid4())
    request.state.request_id = request_id
    start_time = time.time()
    request.state.request_started_at = start_time

    # contextualize() sets a ContextVar that every `get_logger(__name__)` call
    # call inside the request scope will pick up automatically.
    with logger.contextualize(request_id=request_id):
        audit_token = begin_audit_context(
            request.method,
            request.url.path,
            request.client.host if request.client else None,
            request_id=request_id,
        )
        logger.info(f"📥 {request.method} {request.url.path}")

        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            logger.info(
                f"📤 {request.method} {request.url.path} "
                f"- {response.status_code} ({process_time:.3f}s)"
            )
            response.headers["X-Process-Time"] = str(process_time)
        except Exception:
            process_time = time.time() - start_time
            logger.error(
                f"📤 {request.method} {request.url.path} "
                f"- ERROR ({process_time:.3f}s)"
            )
            try:
                await record_request_outcome_safely(request, 500)
            finally:
                reset_audit_context(audit_token)
            raise
        except BaseException:
            # Cancellation and shutdown exceptions still require context cleanup.
            reset_audit_context(audit_token)
            raise

        # Always expose the correlation ID so clients can cross-reference
        # with server-side file logs and DB audit entries.
        response.headers["X-Request-ID"] = request_id

        try:
            await record_request_outcome_safely(request, response.status_code)
        finally:
            reset_audit_context(audit_token)

        return response
    
# ==================== API router====================
from app.api.admin.llm import router as admin_llm_router
app.include_router(admin_llm_router,prefix="/api/v1/admin/llms", tags=["Admin - LLM"])

from app.api.admin.embedding import router as admin_embdding_router
app.include_router(admin_embdding_router,prefix="/api/v1/admin/embeddings", tags=["Admin - Embedding"])

from app.api.admin.user import router as admin_user_router
app.include_router(admin_user_router,prefix="/api/v1/admin/users", tags=["Admin - User"])

from app.api.admin.role import router as admin_role_router
app.include_router(admin_role_router,prefix="/api/v1/admin/roles", tags=["Admin - Role"])

from app.api.admin.menu import router as admin_menu_router
app.include_router(admin_menu_router,prefix="/api/v1/admin/menus", tags=["Admin - Menu"])

from app.api.admin.tool import router as admin_tool_router
app.include_router(admin_tool_router,prefix="/api/v1/admin/tools", tags=["Admin - Tool"])

from app.api.admin.agent import router as admin_agent_router
app.include_router(admin_agent_router,prefix="/api/v1/admin/agents", tags=["Admin - Agent"])

from app.api.admin.domain import router as admin_domain_router
app.include_router(admin_domain_router,prefix="/api/v1/admin/domains", tags=["Admin - Domain"])

from app.api.admin.router_config import router as admin_router_config
app.include_router(admin_router_config,prefix="/api/v1/admin/router-configs", tags=["Admin - Router Config"])

from app.api.admin.strategy_config import router as admin_strategy_config
app.include_router(admin_strategy_config,prefix="/api/v1/admin/strategy-configs", tags=["Admin - Strategy Config"])

from app.api.admin.knowledge_base import router as admin_kownledge_base
app.include_router(admin_kownledge_base,prefix="/api/v1/admin/knowledge-bases", tags=["Admin - Knowledge Base"])

from app.api.admin.document import router as admin_document_router
app.include_router(admin_document_router,prefix="/api/v1/admin/documents", tags=["Admin - Document"])

from app.api.admin.sql_agent import router as admin_sql_agent_router
app.include_router(admin_sql_agent_router,prefix="/api/v1/admin/sql-agent", tags=["Admin - SQL Agent"])

from app.api.admin.task import router as admin_task_router
app.include_router(admin_task_router,prefix="/api/v1/admin/tasks", tags=["Admin - Task"])

from app.api.admin.object_cache import router as admin_object_cache_router
app.include_router(admin_object_cache_router,prefix="/api/v1/admin/object-cache", tags=["Admin - Object Cache"])

from app.api.admin.value_cache import router as admin_value_cache_router
app.include_router(admin_value_cache_router,prefix="/api/v1/admin/value-cache", tags=["Admin - Value Cache"])

from app.api.admin.conversation import router as admin_conversation_router
app.include_router(admin_conversation_router,prefix="/api/v1/admin/conversation", tags=["Admin - Conversation"])

from app.api.admin.prompt import router as admin_prompt_router
app.include_router(admin_prompt_router,prefix="/api/v1/admin/prompts", tags=["Admin - Prompt"])

from app.api.admin.system_setting import router as admin_system_setting_router
app.include_router(admin_system_setting_router,prefix="/api/v1/admin/system-settings", tags=["Admin - System Setting"])

from app.api.admin.audit_log import router as admin_audit_log_router
app.include_router(admin_audit_log_router,prefix="/api/v1/admin/audit-logs", tags=["Admin - Audit Log"])

from app.api.admin.login_log import router as admin_login_log_router
app.include_router(admin_login_log_router,prefix="/api/v1/admin/login-logs", tags=["Admin - Login Log"])

from app.api.user.agent import router as agent_router
app.include_router(agent_router,prefix="/api/v1/agent", tags=["Agent"])

from app.api.user.kb import router as kb_router
app.include_router(kb_router,prefix="/api/v1/kb", tags=["Knowledge Base"])

from app.api.user.sql_agent import router as sql_agent_router
app.include_router(sql_agent_router,prefix="/api/v1/sql-agent", tags=["SQL Agent"])

from app.api.user.web_search import router as web_search_router
app.include_router(web_search_router,prefix="/api/v1/skill", tags=["Skill - Web Search"])

from app.api.integrations.virtual_court.judge import router as virtual_court_judge_router
app.include_router(
    virtual_court_judge_router,
    prefix="/api/v1/integrations/virtual-court",
    tags=["Integration - VirtualCourt"],
)

from app.api.auth.login import router as auth_router
app.include_router(auth_router,prefix="/api/v1",tags=["Security"])

from app.api.auth.menu import router as menu_router
app.include_router(menu_router,prefix="/api/v1",tags=["Security"])

from app.api.auth.permission import router as permission_router
app.include_router(permission_router,prefix="/api/v1",tags=["Permission"])

from app.api.operations import router as operations_router
app.include_router(operations_router)

# ==================== Development server ====================

if __name__ == "__main__":
    import uvicorn
    
    logger.info("=" * 60)
    logger.info(f"🚀 Start the  {settings.app_name} server...")
    logger.info(f"📍 Visit http://{settings.api_host}:{settings.api_port}")
    logger.info(f"📚 API document: http://{settings.api_host}:{settings.api_port}/docs")
    logger.info(f"💾 Databse: {settings.get_sqlite_path()}")
    logger.info("=" * 60)
    
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )

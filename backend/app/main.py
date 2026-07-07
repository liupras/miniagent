#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-10
# @description: MiniAgent FastAPI Main Entr,Provides a RESTful API interface for managing intelligent agents, knowledge bases, and conversations.

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
import time
from typing import AsyncGenerator

# Important: logger_config must be imported before other imports.
# This ensures that the logging system is configured before the entire application starts.
from app.core.logger_config import logger

from app.core.config import settings
from app.infra.db.initializer import db_manager, init_database_on_startup

from app.core.service_container import ServiceContainer
from app.schemas.common import ApiResponse, BaseDomainError, NotFoundError, AlreadyExistsError

from app.core.i18n.i18n import t

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
    debug=settings.debug
)

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
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Record all HTTP requests"""
    start_time = time.time()
    logger.info(f"📥 {request.method} {request.url.path}")
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(f"📤 {request.method} {request.url.path} - {response.status_code}")
        response.headers["X-Process-Time"] = str(process_time)
        return response
    except Exception as exc:
        # Re-eject after logging
        process_time = time.time() - start_time
        logger.error(f"📤 {request.method} {request.url.path} - ERROR ({process_time:.3f}s)")
        return handle_exception(exc)
    
# ==================== Exception handling ====================

def create_api_response(
    code: int = 200,
    message: str = "success",
    data: any = None,
    status_code: int = 200
) -> JSONResponse:
    """Create JSON response from ApiResponse Pydantic model
    
    Convert the ApiResponse Pydantic model to JSONResponse, 
    retaining all Pydantic functionality (validation, serialization, ORM integration, etc.), 
    while also supporting direct return of exception handlers.
    
    Args:
        code: Business status code (200 = success)
        message: Human-readable message
        data: Response payload
        status_code: HTTP status code (always 200 for API responses)
    
    Returns:
        JSONResponse that can be returned from exception handlers
    """
    api_resp = ApiResponse(code=code, message=message, data=data)
    return JSONResponse(
        status_code=status_code,
        content=api_resp.model_dump(exclude_none=True)
    )

def handle_exception(exc: Exception) -> JSONResponse:
    """Global exception handling"""

    if isinstance(exc, NotFoundError):
        logger.warning(f"⚠️  NotFoundError: {exc}")
        return create_api_response(status_code=404,code=404, message=exc.to_detail())
    
    elif isinstance(exc, AlreadyExistsError):
        logger.warning(f"⚠️  AlreadyExistsError: {exc}")
        return create_api_response(status_code=409,code=409, message=exc.to_detail())
    
    elif isinstance(exc, BaseDomainError):
        logger.warning(f"⚠️  BaseDomainError: {exc}")
        return create_api_response(status_code=400,code=400, message=exc.to_detail())
    
    # Handle other exceptions
    logger.error(f"❌ Unhandled exception: {exc}")
    logger.exception(f"❌ Unhandled exception: {exc}")
    
    error_data = {"error": str(exc) if settings.debug else t("common.error_500")}
    return create_api_response(status_code=500,code=500, message=t("common.error_500"), data=error_data)
    
# ==================== API router====================
from app.api.admin.llm import router as admin_llm_router
app.include_router(admin_llm_router,prefix="/api/v1/admin/llms", tags=["Admin - LLM"])

from app.api.admin.embedding import router as admin_embdding_router
app.include_router(admin_embdding_router,prefix="/api/v1/admin/embeddings", tags=["Admin - Embedding"])

from app.api.admin.user import router as admin_user_router
app.include_router(admin_user_router,prefix="/api/v1/admin/users", tags=["Admin - User"])

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

from app.api.user.agent import router as agent_router
app.include_router(agent_router,prefix="/api/v1/agent", tags=["Agent"])

from app.api.user.kb import router as kb_router
app.include_router(kb_router,prefix="/api/v1/kb", tags=["Knowledge Base"])

from app.api.user.sql_agent import router as sql_agent_router
app.include_router(sql_agent_router,prefix="/api/v1/sql-agent", tags=["SQL Agent"])

from app.api.user.web_search import router as web_search_router
app.include_router(web_search_router,prefix="/api/v1/skill", tags=["Skill - Web Search"])

from app.api.auth.login import router as auth_router
app.include_router(auth_router,prefix="/api/v1",tags=["Security"])

from app.api.auth.menu import router as menu_router
app.include_router(menu_router,prefix="/api/v1",tags=["Security"])

from app.api.auth.permission import router as permission_router
app.include_router(permission_router,prefix="/api/v1",tags=["Permission"])

# ==================== Basic routing ====================

@app.get("/",tags=["Operations and maintenance"])
async def root():
    """Basic routing"""
    return {
        "message": f"Welcome to {settings.app_name}!",
        "version": settings.app_version,
        "docs": "/docs",
        "status": "running"
    }

@app.get("/health",tags=["Operations and maintenance"])
async def health_check():
    """Health check"""    
    
    # Check database connection
    db_healthy = False
    try:
        db_healthy = db_manager.check_database()
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
    
    return {
        "status": "healthy" if db_healthy else "unhealthy",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "database": "connected" if db_healthy else "disconnected",
        "timestamp": time.time()
    }


@app.get("/config",tags=["Operations and maintenance"])
async def get_config():
    """Get configuration information (available only in debug mode)"""
    if not settings.debug:
        return JSONResponse(
            status_code=403,
            content={"error": "This endpoint is only available in debug mode"}
        )
    
    return {
        "app_name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "sqlite_path": str(settings.get_sqlite_path()),
        "chroma_path": str(settings.get_vector_db_path()),
        "log_level": settings.log_level
    }


@app.get("/db/info",tags=["Operations and maintenance"])
async def database_info():
    """Retrieve database information"""
    from sqlalchemy import inspect
    
    try:
        inspector = inspect(db_manager.engine)
        tables = inspector.get_table_names()
        
        table_info = {}
        db = db_manager.get_session()
        try:
            # Get the number of records in each table
            from app.infra.db.database import User, Agent, LLM, Embedding, KnowledgeBase, Tool
            
            table_info = {
                "users": db.query(User).count(),
                "agents": db.query(Agent).count(),
                "llm_configs": db.query(LLM).count(),
                "embedding_configs": db.query(Embedding).count(),
                "knowledge_bases": db.query(KnowledgeBase).count(),
                "tools": db.query(Tool).count(),
            }
        finally:
            db.close()
        
        return {
            "database_path": str(settings.get_sqlite_path()),
            "tables": tables,
            "table_count": len(tables),
            "record_counts": table_info
        }
    except Exception as e:
        logger.error(f"Failed to retrieve database information: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

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

#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-07-20
# @description: Operations, maintenance, and administrator system-status routes.

import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy import inspect

from app.core.config import settings
from app.core.security.auth_permission import AuthPermission
from app.infra.db.database import Agent, Embedding, KnowledgeBase, LLM, Tool, User
from app.infra.db.initializer import db_manager
from app.schemas.common import ApiResponse
from app.services.admin.system_status import SystemStatusService

router = APIRouter(tags=["Operations and maintenance"])
_admin_status = AuthPermission.Permission("system_setting:list")


@router.get("/")
async def root():
    """Basic routing."""
    return {
        "message": f"Welcome to {settings.app_name}!",
        "version": settings.app_version,
        "docs": "/docs",
        "status": "running",
    }


@router.get("/health")
async def health_check():
    """Public lightweight API and SQLite health check."""
    db_healthy = False
    try:
        db_healthy = db_manager.check_database()
    except Exception as exc:
        logger.error(f"Database health check failed: {exc}")

    return {
        "status": "healthy" if db_healthy else "unhealthy",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "database": "connected" if db_healthy else "disconnected",
        "timestamp": time.time(),
    }


@router.get("/config")
async def get_config():
    """Get non-secret configuration information in debug mode."""
    if not settings.debug:
        return JSONResponse(
            status_code=403,
            content={"error": "This endpoint is only available in debug mode"},
        )

    return {
        "app_name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "sqlite_path": str(settings.get_sqlite_path()),
        "duckdb_path": str(settings.get_duck_db_path()),
        "chroma_path": str(settings.get_vector_db_path()),
        "log_level": settings.log_level,
    }


@router.get("/db/info")
async def database_info():
    """Retrieve SQLite table and record-count information."""
    try:
        tables = inspect(db_manager.engine).get_table_names()
        db = db_manager.get_session()
        try:
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
            "record_counts": table_info,
        }
    except Exception as exc:
        logger.error(f"Failed to retrieve database information: {exc}")
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get(
    "/api/v1/admin/system/status",
    response_model=ApiResponse,
    summary="Get API and dependency health status",
)
async def system_status(
    request: Request,
    caller_id: int = Depends(_admin_status),
):
    service = SystemStatusService(request.app.state.container)
    return ApiResponse(data=await service.get_status())

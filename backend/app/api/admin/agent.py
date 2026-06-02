#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-29
# @description: Agent API Router – HTTP layer only, all logic lives in AgentService

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.schemas.common import ApiResponse
from app.schemas.admin.agent import AgentCreate, AgentUpdate, AgentOut, AgentListParams,AgentUserUpdate
from app.services.admin.agent import AgentService, AgentNotFoundError, AgentNameConflictError
from app.core.security.auth_permission import AuthPermission

router = APIRouter()

# ──────────────────────────────────────────────
# Service dependency
# ──────────────────────────────────────────────

def get_agent_service(request: Request) -> AgentService:
    return request.app.state.container.agent_service

# ──────────────────────────────────────────────
# Permission dependencies — built once at module level.
# AuthPermission.Permission is self-contained: it resolves
# `request.app.state.container.auth` at call time, so no
# container reference is needed here at import time.
# ──────────────────────────────────────────────

_list   = AuthPermission.Permission("agent:list")
_add    = AuthPermission.Permission("agent:add")
_edit   = AuthPermission.Permission("agent:edit")
_delete = AuthPermission.Permission("agent:delete")

# ──────────────────────────────────────────────
# Exception → HTTP mapping helpers
# ──────────────────────────────────────────────

def _raise_not_found(exc: AgentNotFoundError) -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

def _raise_conflict(exc: AgentNameConflictError) -> None:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@router.get("", response_model=ApiResponse, summary="Paginated agent list  [agent:list]")
async def list_agents(
    page:      int            = Query(1,    ge=1,         description="Page number"),
    page_size: int            = Query(20,   ge=1, le=100, description="Items per page"),
    name:      Optional[str]  = Query(None,               description="Fuzzy filter by agent name"),
    llm_id:    Optional[int]  = Query(None,               description="Filter by LLM id"),
    user_id:   Optional[int]  = Query(None,               description="Filter by bound user id"),
    is_active: Optional[bool] = Query(None,               description="Filter by active status"),
    svc:       AgentService   = Depends(get_agent_service),
    caller_id: int            = Depends(_list),
):
    params = AgentListParams(
        page=page, page_size=page_size,
        name=name, llm_id=llm_id,
        user_id=user_id, is_active=is_active,
    )
    list = await svc.list_agents(params)
    result = ApiResponse(data=list)
    return result


@router.get("/{agent_id}", response_model=ApiResponse, summary="Get agent by id  [agent:list]")
async def get_agent(
    agent_id:  int,
    svc:       AgentService = Depends(get_agent_service),
    caller_id: int          = Depends(_list),
):
    try:
        agent = await svc.get_agent(agent_id)
    except AgentNotFoundError as exc:
        _raise_not_found(exc)
    return ApiResponse(data=AgentOut.model_validate(agent))


@router.post("", response_model=ApiResponse, status_code=status.HTTP_201_CREATED,
             summary="Create agent  [agent:add]")
async def create_agent(
    payload:   AgentCreate,
    svc:       AgentService = Depends(get_agent_service),
    caller_id: int          = Depends(_add),
):
    try:
        agent_out = await svc.create_agent(payload)
    except AgentNameConflictError as exc:
        _raise_conflict(exc)
    return ApiResponse(data=agent_out)


@router.put("/{agent_id}", response_model=ApiResponse, summary="Update agent  [agent:edit]")
async def update_agent(
    agent_id:  int,
    payload:   AgentUpdate,
    svc:       AgentService = Depends(get_agent_service),
    caller_id: int          = Depends(_edit),
):
    try:
        agent_out = await svc.update_agent(agent_id, payload)
    except AgentNotFoundError as exc:
        _raise_not_found(exc)
    except AgentNameConflictError as exc:
        _raise_conflict(exc)
    return ApiResponse(data=agent_out)


@router.patch("/{agent_id}/toggle", response_model=ApiResponse,
              summary="Toggle agent active status  [agent:edit]")
async def toggle_agent_active(
    agent_id:  int,
    svc:       AgentService = Depends(get_agent_service),
    caller_id: int          = Depends(_edit),
):
    try:
        new_state: bool = await svc.toggle_active(agent_id)
    except AgentNotFoundError as exc:
        _raise_not_found(exc)
    verb = "activated" if new_state else "deactivated"
    return ApiResponse(message=f"Agent {verb} successfully")


@router.delete("/{agent_id}", response_model=ApiResponse, summary="Delete agent  [agent:delete]")
async def delete_agent(
    agent_id:  int,
    svc:       AgentService = Depends(get_agent_service),
    caller_id: int          = Depends(_delete),
):
    try:
        await svc.delete_agent(agent_id)
    except AgentNotFoundError as exc:
        _raise_not_found(exc)
    return ApiResponse(message="Agent deleted successfully")


@router.delete("", response_model=ApiResponse, summary="Batch delete agents  [agent:delete]")
async def batch_delete_agents(
    ids:       List[int],
    svc:       AgentService = Depends(get_agent_service),
    caller_id: int          = Depends(_delete),
):
    deleted_count = await svc.batch_delete_agents(ids)
    return ApiResponse(message=f"Deleted {deleted_count} agents")

@router.get("/{agent_id}/users", response_model=ApiResponse, summary="Get users bound to agent [agent:list]")
async def get_users_by_agent(
    agent_id: int,
    svc: AgentService = Depends(get_agent_service),
    caller_id: int = Depends(_list),
):
    """
    Retrieves a list of all users associated with the specified Agent.
    """
 
    users = await svc.get_users_by_agent(agent_id)        
    return ApiResponse(data=users)

@router.put(
    "/{agent_id}/users",
    response_model=ApiResponse[None]
)
async def update_agent_users(
    agent_id: int,
    data: AgentUserUpdate,
    svc: AgentService = Depends(get_agent_service),    
    caller_id: int = Depends(_edit),    
):
    await svc.update_agent_users(
        agent_id,
        data.user_ids
    )

    return ApiResponse()
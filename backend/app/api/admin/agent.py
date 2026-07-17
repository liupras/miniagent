#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-29
# @description: Agent API Router – HTTP layer only, all logic lives in AgentService

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request, status

from app.schemas.common import ApiResponse
from app.schemas.admin.agent import AgentCreate, AgentUpdate, AgentOut, AgentListParams,AgentUserUpdate, AgentToolUpdate
from app.services.admin.agent import AgentService
from app.core.security.auth_permission import AuthPermission

router = APIRouter()

# ──────────────────────────────────────────────
# Service dependency
# ──────────────────────────────────────────────

def get_service(request: Request) -> AgentService:
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
    svc:       AgentService   = Depends(get_service),
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
    svc:       AgentService = Depends(get_service),
    caller_id: int          = Depends(_list),
):
    agent = await svc.get_agent(agent_id)
    return ApiResponse(data=AgentOut.model_validate(agent))


@router.post("", response_model=ApiResponse, status_code=status.HTTP_201_CREATED,
             summary="Create agent  [agent:add]")
async def create_agent(
    payload:   AgentCreate,
    svc:       AgentService = Depends(get_service),
    caller_id: int          = Depends(_add),
):
    
    agent_out = await svc.create_agent(payload)    
    return ApiResponse(data=agent_out)


@router.put("/{agent_id}", response_model=ApiResponse, summary="Update agent  [agent:edit]")
async def update_agent(
    agent_id:  int,
    payload:   AgentUpdate,
    svc:       AgentService = Depends(get_service),
    caller_id: int          = Depends(_edit),
):
   
    agent_out = await svc.update_agent(agent_id, payload)
    return ApiResponse(data=agent_out)


@router.patch("/{agent_id}/toggle", response_model=ApiResponse,
              summary="Toggle agent active status  [agent:edit]")
async def toggle_agent_active(
    agent_id:  int,
    svc:       AgentService = Depends(get_service),
    caller_id: int          = Depends(_edit),
):

    await svc.toggle_active(agent_id)
    return ApiResponse()


@router.delete("/{agent_id}", response_model=ApiResponse, summary="Delete agent  [agent:delete]")
async def delete_agent(
    agent_id:  int,
    svc:       AgentService = Depends(get_service),
    caller_id: int          = Depends(_delete),
):

    await svc.delete_agent(agent_id)
    return ApiResponse()


@router.delete("", response_model=ApiResponse, summary="Batch delete agents  [agent:delete]")
async def batch_delete_agents(
    ids:       List[int],
    svc:       AgentService = Depends(get_service),
    caller_id: int          = Depends(_delete),
):
    deleted_count = await svc.batch_delete_agents(ids)
    return ApiResponse(message=f"Deleted {deleted_count} agents")

@router.get("/{agent_id}/users", response_model=ApiResponse, summary="Get users bound to agent [agent:list]")
async def get_users_by_agent(
    agent_id: int,
    svc: AgentService = Depends(get_service),
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
    svc: AgentService = Depends(get_service),    
    caller_id: int = Depends(_edit),    
):
    await svc.update_agent_users(
        agent_id,
        data.user_ids
    )

    return ApiResponse()

@router.get("/tools/options", response_model=ApiResponse, summary="Get active tool options [agent:list]")
async def get_tool_options(
    svc: AgentService = Depends(get_service),
    caller_id: int = Depends(_list),
):
    tools = await svc.list_active_tools()
    return ApiResponse(data=tools)

@router.get("/{agent_id}/tools", response_model=ApiResponse, summary="Get tools bound to agent [agent:list]")
async def get_tools_by_agent(
    agent_id: int,
    svc: AgentService = Depends(get_service),
    caller_id: int = Depends(_list),
):

    tools = await svc.get_agent_tools(agent_id)
    return ApiResponse(data=tools)

@router.put("/{agent_id}/tools", response_model=ApiResponse[None], summary="Update agent tools [agent:edit]")
async def update_agent_tools(
    agent_id: int,
    data: AgentToolUpdate,
    svc: AgentService = Depends(get_service),
    caller_id: int = Depends(_edit),
):
    await svc.update_agent_tools(agent_id, data.tool_ids)
    return ApiResponse()


@router.get("/{agent_id}/llm", response_model=ApiResponse, summary="Get LLM bound to agent [agent:list]")
async def get_agent_llm(
    agent_id: int,
    svc: AgentService = Depends(get_service),
    caller_id: int = Depends(_list),
):

    llm = await svc.get_agent_llm(agent_id)        
    return ApiResponse(data=llm)

@router.put("/{agent_id}/llm", response_model=ApiResponse[None], summary="Update agent llm binding")
async def update_agent_llm(
    agent_id: int,
    llm_id: int,
    svc: AgentService = Depends(get_service),
    caller_id: int = Depends(_edit),
):
    await svc.update_agent_llm(agent_id, llm_id)
    return ApiResponse()
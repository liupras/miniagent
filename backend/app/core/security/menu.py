#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-28
# @description: Menu and permission management, providing dynamic route data for the frontend based on user permissions.

from fastapi import Request,Depends,APIRouter
import json

from app.core.deps import get_current_user
from app.models.route import ApiResponse, RouteItem
from app.services.route_service import RouteService

router = APIRouter()

def get_route_service(request: Request) -> RouteService:
    return request.app.state.container.route_service

@router.get(
    "/get-async-routes",
    response_model=ApiResponse[list[RouteItem]],
    response_model_exclude_none=True,
    summary="Get the current user's dynamic routing menu and permissions.",
)
async def get_async_routes(
    username: str = Depends(get_current_user),
    route_service: RouteService = Depends(get_route_service),
):
    routes = await route_service.get_user_routes(username)
    #json_string = json.dumps(routes, ensure_ascii=False, indent=2, default=vars)
    #print(json_string)
    return ApiResponse(data=routes)

@router.get("/get-async-routes_mock", summary="Mock version of the dynamic route menu and permissions for the current user.")
async def get_async_routes_mock():
    """Mock version of the dynamic route menu and permissions for the current user."""

    permission_router = {
        "path": "/permission",
        "meta": {
            "title": "menus.purePermission",
            "icon": "ep:lollipop",
            "rank": 10
        },
        "children": [
            {
                "path": "/permission/page/index",
                "name": "PermissionPage",
                "meta": {
                    "title": "menus.purePermissionPage",
                    "roles": ["admin", "common"]
                }
            },
            {
                "path": "/permission/button",
                "meta": {
                    "title": "menus.purePermissionButton",
                    "roles": ["admin", "common"]
                },
                "children": [
                    {
                        "path": "/permission/button/router",
                        "component": "permission/button/index",
                        "name": "PermissionButtonRouter",
                        "meta": {
                            "title": "menus.purePermissionButtonRouter",
                            "auths": [
                                "permission:btn:add",
                                "permission:btn:edit",
                                "permission:btn:delete"
                            ]
                        }
                    }
                ]
            }
        ]
    }

    return {
        "success": True,
        "data": [permission_router]
    }

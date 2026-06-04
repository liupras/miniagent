#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-23
# @description: route service

from app.schemas.auth.route import RouteItem, RouteMeta
from app.core.constants import SUPER_PERMISSION

class RouteService:

    def __init__(self, container):
        from app.core.service_container import ServiceContainer
        if not isinstance(container, ServiceContainer):
            raise TypeError(f"Expected ServiceContainer, got {type(container)}")
        self._menu_db = container.menu_db

    async def get_user_routes(self, username: str) -> list[RouteItem]:
        """
        Query the menus and permissions bound to all user roles,
        and construct the pureAdmin route tree.
        """
        role_codes, menu_map, perm_codes = await self._menu_db.get_user_routes(username)

        def build_tree(parent_id: int | None) -> list[RouteItem]:

            # Buttons are filtered out; they are only used to collect authentication data and not as route nodes.
            children_menus = sorted(
                [m for m in menu_map.values()
                 if m.parent_id == parent_id and m.menu_type != "button"],
                key=lambda m: m.sort_order,
            )

            nodes: list[RouteItem] = []
            for menu in children_menus:

                button_auths = [
                    m.name
                    for m in menu_map.values()
                    if m.parent_id == menu.id
                    and m.menu_type == "button"
                    and (m.name in perm_codes or SUPER_PERMISSION in perm_codes)
                ] or None
                menu_auth = menu.name

                auths = button_auths or []
                auths.append(menu_auth)              

                subtree = build_tree(menu.id) or None

                meta = RouteMeta(
                    title=menu.title_key,
                    icon=menu.icon or None,
                    rank=(menu.sort_order or 1000) if menu.parent_id is None else None,
                    roles=role_codes or None,
                    auths=auths or [],
                )

                node = RouteItem(
                    path=menu.path,
                    name=menu.name,
                    component=menu.component or None,
                    meta=meta,
                    children=subtree, 
                )
                nodes.append(node)

            return nodes

        return build_tree(parent_id=None)
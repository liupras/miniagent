#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-23
# @description: route service

from app.models.route import RouteItem, RouteMeta

class RouteService:

    def __init__(
        self,
        container
    ):
        from app.core.service_container import ServiceContainer
        if not isinstance(container, ServiceContainer):
            raise TypeError(f"Expected ServiceContainer, got {type(container)}")
        
        self._menu_db = container.menu_db

    async def get_user_routes(self,username: str) -> list[RouteItem]:
        """
        Query the menus and permissions bound to all user roles, and construct the pureAdmin route tree.
        """

        role_codes, menu_map,perm_codes = await self._menu_db.get_user_routes(username)

        # ── Build the menu tree (only keep nodes whose parent_id is also in the menu_map)────────────────
        def build_tree(parent_id: int | None) -> list[RouteItem]:
            children_menus = sorted(
                [m for m in menu_map.values() if m.parent_id == parent_id],
                key=lambda m: m.sort_order,
            )
            nodes: list[RouteItem] = []
            for menu in children_menus:
                subtree = build_tree(menu.id)

                # This section collects the permission codes of the button's child nodes into the current node's auths.
                button_auths = [
                    m.name  # The button node uses the name field to store the code.
                    for m in menu_map.values()
                    if m.parent_id == menu.id and m.menu_type == "button"
                    and m.name in perm_codes
                ]

                meta = RouteMeta(
                    title=menu.title_key,
                    icon=menu.icon or None,
                    rank=menu.sort_order if menu.parent_id is None else None,
                    roles=role_codes if role_codes else None,
                    auths=button_auths if button_auths else None,
                )

                node = RouteItem(
                    path=menu.path,
                    name=menu.name if menu.menu_type != "directory" else None,
                    component=menu.component or None,
                    meta=meta,
                    children=subtree if subtree else None,
                )
                nodes.append(node)
            return nodes

        return build_tree(parent_id=None)
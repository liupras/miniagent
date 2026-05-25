#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-23
# @description: route service

from app.models.route import RouteItem, RouteMeta

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

            # 需求3：过滤掉 button 类型，button 只用于收集 auths，不作为路由节点
            children_menus = sorted(
                [m for m in menu_map.values()
                 if m.parent_id == parent_id and m.menu_type != "button"],
                key=lambda m: m.sort_order,
            )

            nodes: list[RouteItem] = []
            for menu in children_menus:

                # 需求3：收集当前节点下 button 子节点的 name 作为 auths
                button_auths = [
                    m.name
                    for m in menu_map.values()
                    if m.parent_id == menu.id
                    and m.menu_type == "button"
                    and (m.name in perm_codes or "*:*:*" in perm_codes)  # ← 修复超级管理员判断
                ] or None

                subtree = build_tree(menu.id) or None  # 空列表转 None，配合 exclude_none 不输出 children 字段（需求2）

                meta = RouteMeta(
                    title=menu.title_key,
                    icon=menu.icon or None,
                    # 需求1：仅顶级菜单输出 rank，sort_order 为 null 时兜底 1000
                    rank=(menu.sort_order or 1000) if menu.parent_id is None else None,
                    roles=role_codes or None,
                    auths=button_auths,   # None 时 exclude_none 自动去掉（需求4）
                )

                node = RouteItem(
                    path=menu.path,
                    name=menu.name if menu.menu_type != "directory" else None,
                    component=menu.component or None,
                    meta=meta,
                    children=subtree,     # None 时 exclude_none 自动去掉（需求2）
                )
                nodes.append(node)

            return nodes

        return build_tree(parent_id=None)
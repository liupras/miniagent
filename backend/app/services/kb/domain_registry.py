#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-16
# @description: Domain registry.

from .domain_plugin import DomainPlugin

class DomainRegistry:
    def __init__(self):
        self._plugins: dict[str, DomainPlugin] = {}

    def register(self, domain: str, plugin: DomainPlugin) -> None:
        self._plugins[domain] = plugin

    def get(self, domain: str) -> DomainPlugin:
        # When the domain is not found, it falls back to the general method and never throws an exception.
        return self._plugins.get(domain)
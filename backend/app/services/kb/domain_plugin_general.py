#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-16
# @description: General plugin interface.

from .domain_plugin import DomainPlugin
from .small_to_big_base import SmallToBigProcessor

class GeneralDomainPlugin(DomainPlugin):

    def __init__(self, processor:SmallToBigProcessor):
        self._processor = processor

    @property
    def processor(self)->SmallToBigProcessor:
        return self._processor

    def parse_metadata(self, raw: dict) -> dict:
        return raw or {}
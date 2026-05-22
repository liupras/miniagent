#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-16
# @description: General plugin interface.

from ..domain_plugin import DomainPlugin
from .small_to_big import LawSmallToBigProcessor
from .merger import LawMerger

class LawDomainPlugin(DomainPlugin):

    def __init__(self, processor:LawSmallToBigProcessor):
        self._processor = processor

    @property
    def processor(self)->LawSmallToBigProcessor:
        return self._processor

    def parse_metadata(self, raw: dict) -> dict:
        return raw or {}
    
    @property
    def citation_merger(self) -> LawMerger:
        return LawMerger()
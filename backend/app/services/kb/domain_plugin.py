#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-03-16
# @description: General plugin interface.

from abc import ABC, abstractmethod
from .small_to_big_base import SmallToBigProcessor
from .citation_merger import CitationMerger

class DomainPlugin(ABC):

    @property
    @abstractmethod
    def processor(self)->SmallToBigProcessor:
        """Holds SmallToBig processor instances in this domain"""

    @abstractmethod
    def parse_metadata(self, raw: dict) -> dict:
        """Validate and standardize the document metadata passed during upload."""

    @property
    def citation_merger(self) -> CitationMerger:
        """
        Override to provide a domain-specific citation merger.
        Falls back to DefaultMerger if not overridden.
        """
        return CitationMerger()
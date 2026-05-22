#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-22
# @description: Storage backend interface definition


from abc import ABC, abstractmethod

from typing import BinaryIO

class StorageBackend(ABC):

    @abstractmethod
    def save(self, path: str, data: bytes) -> str:
        pass

    @abstractmethod
    def save_file(
        self,
        path: str,
        file_obj: BinaryIO,
        overwrite: bool = False,
    ) -> str:
        pass

    @abstractmethod
    def read(self, path: str) -> bytes:
        pass

    @abstractmethod
    def delete(self, path: str) -> None:
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        pass

    @abstractmethod
    def url(self, path: str) -> str:
        """
        Return public/internal accessible URL.
        """
        pass

    @abstractmethod
    def stat(self, path: str) -> dict:
        pass
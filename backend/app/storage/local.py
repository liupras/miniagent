#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-22
# @description: Local storage backend implementation

from pathlib import Path
import shutil
from typing import BinaryIO
from app.storage.base import StorageBackend

class LocalStorageBackend(StorageBackend):

    def __init__(self, root_dir: str):
        self.root = Path(root_dir)

    def save(self, path: str, data: bytes) -> str:
        full_path = self._full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        full_path.write_bytes(data)

        return path
    
    def save_file(
        self,
        path: str,
        file_obj: BinaryIO,
        overwrite: bool = False,
    ) -> str:

        full_path = self._full_path(path)

        if full_path.exists() and not overwrite:
            raise FileExistsError(path)

        full_path.parent.mkdir(parents=True, exist_ok=True)

        with open(full_path, "wb") as f:
            shutil.copyfileobj(file_obj, f)

        return path

    def read(self, path: str) -> bytes:
        return (self._full_path(path)).read_bytes()

    def delete(self, path: str) -> None:
        p = self._full_path(path)
        if p.exists():
            p.unlink()

    def exists(self, path: str) -> bool:
        return self._full_path(path).exists()
    
    def url(self, path: str) -> str:
        return f"{self._full_path(path).as_uri()}"

    def stat(self, path: str) -> dict:

        full_path = self._full_path(path)
        stat = full_path.stat()
        return {
            "size": stat.st_size,
            "mtime": stat.st_mtime,
        }
    
    def _full_path(self, path: str) -> Path:
        return self.root / path
#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-22
# @description: Storage manager that initializes the appropriate storage backend based on configuration

from app.core.config import settings
from app.storage.local import LocalStorageBackend

storage = LocalStorageBackend(root_dir=settings.get_storage_dir())
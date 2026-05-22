#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-22
# @description: Storage manager that initializes the appropriate storage backend based on configuration

from app.storage.local import LocalStorageBackend

storage = LocalStorageBackend(root_dir="./data/storage")
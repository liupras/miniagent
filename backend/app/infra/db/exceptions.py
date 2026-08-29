#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-08-29
# @description: Stable application errors for database infrastructure.

from app.schemas.exceptions import InfrastructureError


class DatabaseInitializationError(InfrastructureError):
    """The required application database could not be prepared."""

    error_key = "database.initialization_failed"

    def __init__(self) -> None:
        super().__init__("Database initialization failed")

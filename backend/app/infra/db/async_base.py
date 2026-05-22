#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-15
# @description: SQLAlchemy Asynchronous Base Database Manager

from contextlib import asynccontextmanager
from sqlalchemy.exc import SQLAlchemyError

class AsyncBaseDatabase:
    """SQLAlchemy Asynchronous Database Base Class"""

    def __init__(self, engine, session_factory):
        self.engine = engine
        self.AsyncSessionLocal = session_factory

    @asynccontextmanager
    async def get_session(self):
        """Asynchronous Session Context Manager"""
        async with self.AsyncSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                raise
            finally:
                await session.close()
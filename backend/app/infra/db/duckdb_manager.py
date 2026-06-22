#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-03
# @description: duckdb manager

import duckdb

from app.core.config import settings

class DuckDBManager:
    def __init__(self, db_path: str):
        self.conn = duckdb.connect(db_path)

    def execute(self, sql, params=None):
        return self.conn.execute(sql, params or []).fetchall()

    def close(self):
        self.conn.close()

# Global instance
duckdb_manager = DuckDBManager(settings.get_duck_db_path() / "duckdb.db")
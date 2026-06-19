#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-30
# @description: db manager

import pandas as pd
from loguru import logger
import os

from ...infra.db.duckdb_manager import DuckDBManager

class DBManager:

    # The key is a Python/Pandas type name, and the value is the corresponding DuckDB type name.
    TYPE_MAP = {
        'int64': 'BIGINT',
        'float64': 'DOUBLE',
        'bool': 'BOOLEAN',
        'datetime64[ns]': 'TIMESTAMP',
        'object': 'VARCHAR'
    }

    def __init__(self, duckdb_manager:DuckDBManager):        
        self._conn = duckdb_manager.conn

    def _get_duckdb_type(self, pandas_series) -> str:
        """Get the recommended DuckDB type from Pandas Series"""
        dtype_name = str(pandas_series.dtype)
        return self.TYPE_MAP.get(dtype_name, 'VARCHAR')

    def import_csv(self, 
                   file_path: str, 
                   schema_name: str = "main",
                   table_name: str = None, 
                   primary_key: str | list[str] = None,
                   force_cast: bool = False, 
                   allow_new_columns: bool = False):
        """
        Import CSV and automatically perform schema conflict detection logic.
        :param primary_key: Used to detect duplicate primary key column names.
        :param force_cast: Whether to force a cast if column names are the same but types are different.
        :param allow_new_columns: Whether to allow appending new columns if the number of columns is different.
        """
        # 1. Normalized schema and table names
        if not table_name:
            table_name = os.path.basename(file_path).replace(".csv", "")      

        schema_name = self._normalize_identifier(schema_name or "main")
        table_name = self._normalize_identifier(table_name)
        full_table_path = f'"{schema_name}"."{table_name}"'

        # Standardize primary_key as a list (None should remain None).
        if isinstance(primary_key, str):
            pk_cols = [c.strip() for c in primary_key.split(",")]
        elif isinstance(primary_key, list):
            pk_cols = primary_key
        else:
            pk_cols = None

        # 2. Ensure the schema exists
        self._conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')

        # 3. Load data and normalize column names
        df_new = pd.read_csv(file_path)
        df_new.columns = [self._normalize_column_name(c) for c in df_new.columns]

        # 4. Does the table exist?
        table_exists = self._conn.execute(
            """
            SELECT count(*) FROM information_schema.tables 
            WHERE table_schema = ? AND table_name = ?
            """, 
            [schema_name, table_name]
        ).fetchone()[0] > 0

        # 5. If the table does not exist, create the table with a primary key.
        if not table_exists:
            if pk_cols:
                missing = [c for c in pk_cols if c not in df_new.columns]
                if missing:
                    raise ValueError(f"Primary key column(s) {missing} not found in CSV.")
                
                cols_def = []
                for col in df_new.columns:
                    dtype = self._get_duckdb_type(df_new[col])
                    cols_def.append(f'"{col}" {dtype}')

                pk_clause = ", ".join(f'"{c}"' for c in pk_cols)
                cols_def.append(f'PRIMARY KEY ({pk_clause})')

                create_sql = f'CREATE TABLE {full_table_path} ({", ".join(cols_def)})'
                self._conn.execute(create_sql)
                self._conn.execute(f'INSERT INTO {full_table_path} SELECT * FROM df_new')
            else:
                self._conn.execute(f'CREATE TABLE {full_table_path} AS SELECT * FROM df_new')
            
            logger.info(f"Created table {full_table_path}")
            return full_table_path

        # 6. Get existing schema
        existing_info = self._conn.execute(f"DESCRIBE {full_table_path}").df()
        existing_schema = dict(zip(existing_info['column_name'], existing_info['column_type']))

        # 7. Perform conflict detection
        for col in df_new.columns:
            new_type = self._get_duckdb_type(df_new[col])
            
            # Scenario A: New column detection
            if col not in existing_schema:
                if not allow_new_columns:
                    raise ValueError(f"Column '{col}' is missing in database. 'allow_new_columns' is False.")
                self._conn.execute(f'ALTER TABLE {full_table_path} ADD COLUMN "{col}" {new_type}')
                logger.info(f"Added column: {col} ({new_type})")
                continue

            # Scenario B: Type Conflict Detection
            old_type = existing_schema[col].upper()
            if old_type != new_type:
                # Define a whitelist of entities that can be automatically promoted (low-risk conversions).
                safe_promotion = (old_type == 'BIGINT' and new_type == 'DOUBLE') or \
                                 (old_type == 'VARCHAR') # Any data type can usually be converted to VARCHAR.
                
                if not safe_promotion and not force_cast:
                    raise TypeError(
                        f"Type conflict for column '{col}': DB is {old_type}, CSV is {new_type}. "
                        f"Set 'force_cast=True' to override."
                    )
                logger.warning(f"Type promotion for '{col}': {old_type} -> {new_type}")

        # 8. UPSERT or append.
        if pk_cols:
            missing = [c for c in pk_cols if c not in df_new.columns]
            if missing:
                raise ValueError(f"Primary key column(s) {missing} not found in CSV columns.")

            update_cols = [f'"{c}" = EXCLUDED."{c}"' for c in df_new.columns if c not in pk_cols]
            update_stmt = ", ".join(update_cols)

            pk_conflict_clause = ", ".join(f'"{c}"' for c in pk_cols)

            upsert_sql = f"""
                INSERT INTO {full_table_path} BY NAME SELECT * FROM df_new
                ON CONFLICT ({pk_conflict_clause}) 
                DO UPDATE SET {update_stmt}
            """
            try:
                self._conn.execute(upsert_sql)
                logger.success(f"UPSERT completed for {full_table_path} on PK: {pk_cols}")
            except Exception as e:
                logger.error(f"UPSERT failed: {e}")
                raise e
        else:
            # If there is no primary key, revert to normal append logic.
            # Using INSERT INTO ... BY NAME ensures column names are automatically aligned.
            try:
                self._conn.execute(f'INSERT INTO {full_table_path} BY NAME SELECT * FROM df_new')
                logger.warning(f"No primary key provided. Data appended to {full_table_path} (may contain duplicates).")
            except Exception as e:
                logger.error(f"Insert failed: {e}")
                raise e

        return full_table_path

    def _normalize_identifier(self, name: str) -> str:
        name = name.lower()
        return f"{name}_tbl" if name in {"order", "group", "select", "table"} else name

    def _normalize_column_name(self, col: str) -> str:
        col = col.lower().strip().replace(" ", "_")
        return f"{col}_col" if col in {"order", "group", "select"} else col
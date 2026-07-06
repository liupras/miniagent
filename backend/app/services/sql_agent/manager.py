#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-30 (updated 2026-07-06: Excel import + table management)
# @description: db manager

import os

import pandas as pd
from loguru import logger

from app.infra.db.duckdb_manager import DuckDBManager

from app.core.i18n.i18n import t

class DBManager:

    # The key is a Python/Pandas type name, and the value is the corresponding DuckDB type name.
    TYPE_MAP = {
        'int64': 'BIGINT',
        'float64': 'DOUBLE',
        'bool': 'BOOLEAN',
        'datetime64[ns]': 'TIMESTAMP',
        'object': 'VARCHAR'
    }

    def __init__(self, duckdb_manager: DuckDBManager):
        self._conn = duckdb_manager.conn

    def _get_duckdb_type(self, pandas_series) -> str:
        """Get the recommended DuckDB type from Pandas Series"""
        dtype_name = str(pandas_series.dtype)
        return self.TYPE_MAP.get(dtype_name, 'VARCHAR')

    # ─────────────────────────────────────────────────────────────────────
    # Import — unified CSV / Excel entry point
    # ─────────────────────────────────────────────────────────────────────

    def import_table(self,
                      file_path: str,
                      file_type: str = "csv",
                      schema_name: str = "main",
                      table_name: str = None,
                      sheet_name: str | int | None = None,
                      primary_key: str | list[str] = None,
                      force_cast: bool = False,
                      allow_new_columns: bool = False) -> dict:
        """
        Import a CSV or Excel file and automatically perform schema conflict
        detection logic. This is the generalized successor to import_csv();
        the only difference is step 3 (how the file is read into df_new).
        Everything downstream (table creation, conflict detection, upsert)
        is unchanged and format-agnostic since it only ever sees a DataFrame.

        :param file_type: "csv" or "excel". Determines which pandas reader is used.
        :param sheet_name: Excel sheet to read (name or index). Ignored for CSV.
                            Defaults to the first sheet when omitted.
        :param primary_key: Used to detect duplicate primary key column names.
        :param force_cast: Whether to force a cast if column names are the same but types are different.
        :param allow_new_columns: Whether to allow appending new columns if the number of columns is different.
        :return: dict with keys: table_path, row_count, and (for excel) sheet_name.
        """
        if file_type not in ("csv", "excel"):
            raise ValueError(t("sql_agent.unsupported_file_type", file_type=file_type))

        # 1. Normalized schema and table names
        if not table_name:
            base = os.path.basename(file_path)
            table_name, _ = os.path.splitext(base)

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
        resolved_sheet_name = None
        if file_type == "csv":
            df_new = pd.read_csv(file_path)
        else:
            # sheet_name=0 -> first sheet by position when the caller didn't ask for one
            df_new = pd.read_excel(file_path, sheet_name=sheet_name if sheet_name is not None else 0)
            resolved_sheet_name = sheet_name if sheet_name is not None else self._first_sheet_name(file_path)

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
                    raise ValueError(t("sql_agent.primary_key_not_found", missing=", ".join(missing)))

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
            return self._import_result(full_table_path, file_type, resolved_sheet_name)

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
                                 (old_type == 'VARCHAR')  # Any data type can usually be converted to VARCHAR.

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

        return self._import_result(full_table_path, file_type, resolved_sheet_name)

    def import_csv(self,
                    file_path: str,
                    schema_name: str = "main",
                    table_name: str = None,
                    primary_key: str | list[str] = None,
                    force_cast: bool = False,
                    allow_new_columns: bool = False):
        """
        Back-compat wrapper. Existing callers that only ever imported CSV and
        expect a bare table-path string keep working unchanged.
        New code (the /import router) should call import_table() directly.
        """
        result = self.import_table(
            file_path=file_path,
            file_type="csv",
            schema_name=schema_name,
            table_name=table_name,
            primary_key=primary_key,
            force_cast=force_cast,
            allow_new_columns=allow_new_columns,
        )
        return result["table_path"]

    def _import_result(self, full_table_path: str, file_type: str, sheet_name: str | int | None) -> dict:
        row_count = self._conn.execute(f"SELECT COUNT(*) FROM {full_table_path}").fetchone()[0]
        result = {"table_path": full_table_path, "row_count": row_count}
        if file_type == "excel":
            result["sheet_name"] = sheet_name
        return result

    def _first_sheet_name(self, file_path: str) -> str:
        with pd.ExcelFile(file_path) as xls:
            return xls.sheet_names[0]

    # ─────────────────────────────────────────────────────────────────────
    # Table management — list schemas/tables, inspect columns, preview, drop
    # ─────────────────────────────────────────────────────────────────────

    def list_schemas(self) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT table_schema, COUNT(*) AS table_count
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            GROUP BY table_schema
            ORDER BY table_schema
            """
        ).fetchall()
        return [{"schema_name": r[0], "table_count": r[1]} for r in rows]

    def list_tables(self, schema_name: str = "main") -> list[dict]:
        schema_name = self._normalize_identifier(schema_name or "main")
        rows = self._conn.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = ? ORDER BY table_name
            """,
            [schema_name]
        ).fetchall()

        result = []
        for (table_name,) in rows:
            full_table_path = f'"{schema_name}"."{table_name}"'
            row_count = self._conn.execute(f"SELECT COUNT(*) FROM {full_table_path}").fetchone()[0]
            column_count = self._conn.execute(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = ? AND table_name = ?
                """,
                [schema_name, table_name]
            ).fetchone()[0]
            result.append({
                "schema_name": schema_name,
                "table_name": table_name,
                "row_count": row_count,
                "column_count": column_count,
            })
        return result

    def get_table_columns(self, schema_name: str, table_name: str) -> list[dict] | None:
        schema_name = self._normalize_identifier(schema_name or "main")
        table_name = self._normalize_identifier(table_name)

        rows = self._conn.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = ? AND table_name = ?
            ORDER BY ordinal_position
            """,
            [schema_name, table_name]
        ).fetchall()
        if not rows:
            return None

        pk_cols = set(self._primary_key_columns(schema_name, table_name))
        return [
            {
                "name": r[0],
                "type": r[1],
                "nullable": r[2] == "YES",
                "is_primary_key": r[0] in pk_cols,
                "default": r[3],
            }
            for r in rows
        ]

    def _primary_key_columns(self, schema_name: str, table_name: str) -> list[str]:
        try:
            rows = self._conn.execute(
                """
                SELECT constraint_column_names FROM duckdb_constraints()
                WHERE schema_name = ? AND table_name = ? AND constraint_type = 'PRIMARY KEY'
                """,
                [schema_name, table_name]
            ).fetchall()
            return list(rows[0][0]) if rows else []
        except Exception:
            # duckdb_constraints() column names have shifted across DuckDB versions;
            # fall back to "no PK info" rather than blowing up column listing.
            return []

    def preview_table(self,
                       schema_name: str,
                       table_name: str,
                       page: int = 1,
                       page_size: int = 20,
                       order_by: str = None,
                       order_desc: bool = False) -> dict | None:
        schema_name = self._normalize_identifier(schema_name or "main")
        table_name = self._normalize_identifier(table_name)
        full_table_path = f'"{schema_name}"."{table_name}"'

        table_exists = self._conn.execute(
            """
            SELECT count(*) FROM information_schema.tables
            WHERE table_schema = ? AND table_name = ?
            """,
            [schema_name, table_name]
        ).fetchone()[0] > 0
        if not table_exists:
            return None

        columns = self.get_table_columns(schema_name, table_name) or []

        total = self._conn.execute(f"SELECT COUNT(*) FROM {full_table_path}").fetchone()[0]

        order_clause = ""
        if order_by:
            order_by = self._normalize_column_name(order_by)
            direction = "DESC" if order_desc else "ASC"
            order_clause = f' ORDER BY "{order_by}" {direction}'

        offset = max(page - 1, 0) * page_size
        df = self._conn.execute(
            f'SELECT * FROM {full_table_path}{order_clause} LIMIT ? OFFSET ?',
            [page_size, offset]
        ).fetchdf()

        return {
            "columns": columns,
            "rows": df.to_dict(orient="records"),
            "total": total,
        }

    def drop_table(self, schema_name: str, table_name: str) -> bool:
        schema_name = self._normalize_identifier(schema_name or "main")
        table_name = self._normalize_identifier(table_name)

        table_exists = self._conn.execute(
            """
            SELECT count(*) FROM information_schema.tables
            WHERE table_schema = ? AND table_name = ?
            """,
            [schema_name, table_name]
        ).fetchone()[0] > 0
        if not table_exists:
            return False

        self._conn.execute(f'DROP TABLE "{schema_name}"."{table_name}"')
        logger.info(f"Dropped table \"{schema_name}\".\"{table_name}\"")
        return True

    # ─────────────────────────────────────────────────────────────────────
    # Identifier helpers (unchanged from original)
    # ─────────────────────────────────────────────────────────────────────

    def _normalize_identifier(self, name: str) -> str:
        name = name.lower()
        return f"{name}_tbl" if name in {"order", "group", "select", "table"} else name

    def _normalize_column_name(self, col: str) -> str:
        col = col.lower().strip().replace(" ", "_")
        return f"{col}_col" if col in {"order", "group", "select"} else col

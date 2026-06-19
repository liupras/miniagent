#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-30
# @description: sql tools

from typing import List, Dict, Any
import re
from loguru import logger
from .sandbox import run_python_sandbox

from ...infra.db.duckdb_manager import DuckDBManager

class SQLTools:
    def __init__(self, duckdb_manager: DuckDBManager, schema_name: str = "main"):
        self._conn = duckdb_manager.conn
        self._schema = schema_name

    def _is_valid_identifier(self, name: str) -> bool:
        """
        Verify that table or column names are valid identifiers to prevent SQL injection.
        Allow only letters, numbers, and underscores; avoid concatenating special characters.
        """
        return bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name))

    def get_schema(self, table_name: str,schema_name: str = "main") -> List[Dict[str, Any]]:
        """Get Schema - Prevent Injection Using Parameterized Queries"""
        try:
            # Using a question mark (?) as a placeholder, the DuckDB driver will automatically handle the escaping.
            query = """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = ? AND table_name = ?
            """
            result = self._conn.execute(query, [schema_name, table_name]).fetchall()

            if not result:
                return {"error": f"Table '{schema_name}.{table_name}' not found."}

            return [
                {"column": r[0], "type": r[1]}
                for r in result
            ]
        except Exception as e:
            logger.error(f"❌ get_schema failed: {e}")
            return {"error": str(e)}

    def sample_data(self, table_name: str, schema_name: str = "main", limit: int = 3) -> List[Dict[str, Any]]:
        """Data sampling - Strictly validate table names"""
        try:
            # Table names cannot use placeholders and must be manually validated.
            if not self._is_valid_identifier(schema_name) or not self._is_valid_identifier(table_name):
                return {"error": "Invalid schema or table name format."}

            # Limit is restricted to integers to prevent injection.
            limit = int(limit)
            query = f'SELECT * FROM "{schema_name}"."{table_name}" LIMIT {limit}'
            
            df = self._conn.execute(query).fetchdf()
            return df.to_dict(orient="records")
        except Exception as e:
            logger.error(f"❌ sample_data failed: {e}")
            return {"error": str(e)}

    def execute_sql(self, sql: str) -> Any:
        """SQL Execution - Enhanced Security Checks"""
        try:
            # 1.Basic cleanup: Remove comments and line breaks to prevent bypassing simple matching.
            clean_sql = re.sub(r'--.*', '', sql)  # Remove single-line comments
            clean_sql = re.sub(r'/\*.*?\*/', '', clean_sql, flags=re.DOTALL) # Remove multi-line comments
            
            sql_upper = clean_sql.strip().upper()

            # 2. Behavior verification
            if not sql_upper.startswith("SELECT") and not sql_upper.startswith("WITH"):
                return {"error": "Only SELECT or WITH statements are allowed."}

            # 3. Keyword blacklist (adds \b word boundary matching to reduce false positives and improve defense)
            forbidden = [r"\bDROP\b", r"\bDELETE\b", r"\bUPDATE\b", r"\bINSERT\b", r"\bALTER\b", r"\bTRUNCATE\b"]
            if any(re.search(pattern, sql_upper) for pattern in forbidden):
                return {"error": "Forbidden DDL/DML keyword detected."}

            # 4. Forced LIMIT protection
            if "LIMIT" not in sql_upper:
                sql = sql.rstrip().rstrip(";") + " LIMIT 500"

            sql = self._quote_schema_table(sql)

            # 5. Pre-execution validation and cost estimation
            warnings = []
            try:
                # Use EXPLAIN to validate the syntax and obtain the execution plan.
                explain_query = f"EXPLAIN {sql}"
                explain_df = self._conn.execute(explain_query).fetchdf()
                plan_detail = str(explain_df['explain_value'].values[0])

                # Cost estimation logic: Check for costly operations
                # Warning: If a large cross-table join or complex calculation is detected...
                if "CROSS_PRODUCT" in plan_detail or "EMPTY_RESULT" in plan_detail:
                    warnings.append("Detection of potential Cartesian product (CROSS PRODUCT).")
                    logger.warning(f"Potential inefficient query detected: {plan_detail}")                
                                
                # 获取数据库大小作为参考
                db_size_info = self._conn.execute("PRAGMA database_size").fetchdf()
                if not db_size_info.empty:
                    # 计算总字节数: block_size * total_blocks
                    row = db_size_info.iloc[0]
                    total_bytes = int(row['block_size']) * int(row['total_blocks'])
                    gb_size = total_bytes / (1024 ** 3)

                    if "SCAN" in plan_detail and gb_size > 0.5:
                        warn_msg = f"Database size is large ({gb_size:.2f} GB). Query might be slow."
                        logger.warning(warn_msg)
                        warnings.append(warn_msg)
                logger.warning(f"Database size is large: {db_size_info}")
                  
            except Exception as e:
                return {"error": f"SQL Validation failed: {str(e)}"}
            
            df = self._conn.execute(sql).fetchdf()

            return {
                "columns": list(df.columns),
                "rows": df.to_dict(orient="records"),
                "row_count": len(df),
                "warnings": warnings if warnings else None,
            }
        except Exception as e:
            logger.error(f"❌ execute_sql failed: {e}")
            return {"error": str(e)}
        
    def list_tables_metadata(self, schema_name:str="main")->List[Dict[str, str]]:
        try:
            rows = self._conn.execute(
                """
                SELECT table_name, comment FROM duckdb_tables 
                WHERE schema_name = ? ORDER BY table_name
                """,
                [schema_name],
            ).fetchall()
            tables_metadata = [
                {
                    "name": r[0], 
                    "comment": r[1] if r[1] is not None else ""
                } 
                for r in rows
            ]
            return tables_metadata
        except Exception as e:
            logger.error(f"❌ list_all_table_name failed: {e}")
            return []
        
    def run_python(self, code: str) -> Dict[str, Any]:
        """
        Execute Python code in a sandboxed environment.

        The sandbox provides:
        - ``conn``        : read-only DuckDB proxy (SELECT / WITH only)
        - ``schema_name`` : current schema string
        - Whitelisted stdlib + pandas / numpy
        - AST-level import/attribute blocking
        - Optional RestrictedPython bytecode layer
        - 10-second wall-clock timeout (Unix)
        - stdout captured and returned
        """
        logger.info("🐍 run_python called")
        return run_python_sandbox(
            code=code,
            conn=self._conn,
            schema_name=self._schema,
        )
    
    def _quote_schema_table(self, sql: str) -> str:
        # Simply replace schema.table with "schema"."table"
        pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b'
        
        def repl(match):
            schema, table = match.groups()
            return f'"{schema}"."{table}"'
        
        return re.sub(pattern, repl, sql)

    def call_tool(self, name: str, args: Dict[str, Any]) -> Any:
        """Tool distributor (for Agent)"""
        if name == "get_schema":
            return self.get_schema(**args)
        elif name == "sample_data":
            return self.sample_data(**args)
        elif name == "execute_sql":
            return self.execute_sql(**args)
        elif name == "run_python":
            return self.run_python(**args)
        else:
            return {"error": f"Unknown tool: {name}"}
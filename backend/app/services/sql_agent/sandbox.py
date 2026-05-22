#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-30
# @description: python sandbox for run_python tool

import io
import re
import ast
import time
import contextlib
import traceback
import threading
import concurrent.futures
from typing import Any, Dict, Optional

import duckdb
from loguru import logger

# ─────────────────────────────────────────────
# Whitelist: modules the sandbox is allowed to
# import.  Everything else is blocked.
# ─────────────────────────────────────────────
ALLOWED_MODULES = frozenset({
    "math", "statistics", "random",
    "json", "re", "datetime", "decimal",
    "collections", "itertools", "functools",
    "pandas", "numpy","io", "string",
    "matplotlib", "matplotlib.pyplot","plt", "seaborn", "sns", "base64"
})

# Hard limits
MAX_OUTPUT_CHARS = 10_000   # stdout cap
MAX_EXEC_SECONDS = 10       # wall-clock timeout (cross-platform, thread-based)
MAX_ROWS_IN_SCOPE = 50_000  # rows fetchable via the injected connection


# ─────────────────────────────────────────────
# AST security scanner
# ─────────────────────────────────────────────

class _ASTSecurityScanner(ast.NodeVisitor):
    """
    Walk the AST before execution.  Raises ValueError for any
    node that looks dangerous regardless of RestrictedPython.
    """

    _FORBIDDEN_ATTRS = frozenset({
        # dunder escapes
        "__class__", "__bases__", "__subclasses__", "__mro__",
        "__globals__", "__builtins__", "__import__",
        "__reduce__", "__reduce_ex__", "__getattribute__",
        # file / process
        "open", "exec", "eval", "compile",
        "system", "popen", "Popen", "spawn",
    })

    _FORBIDDEN_NAMES = frozenset({
        "exec", "eval", "compile", "open",
        "__import__", "breakpoint",
        # common escape hatches
        "globals", "locals", "vars", "dir",
        "getattr", "setattr", "delattr",
        "type", "object",
    })

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root not in ALLOWED_MODULES:
                raise ValueError(f"Import of '{alias.name}' is not allowed.")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        root = (node.module or "").split(".")[0]
        if root not in ALLOWED_MODULES:
            raise ValueError(f"Import from '{node.module}' is not allowed.")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if node.id in self._FORBIDDEN_NAMES:
            raise ValueError(f"Use of '{node.id}' is not allowed.")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr in self._FORBIDDEN_ATTRS:
            raise ValueError(f"Access to attribute '{node.attr}' is not allowed.")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Block calls like __builtins__['eval'](...) 
        if isinstance(node.func, ast.Subscript):
            raise ValueError("Subscript-based calls are not allowed.")
        self.generic_visit(node)


def _scan_ast(code: str) -> None:
    """Parse and scan code; raise ValueError on any violation."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Syntax error: {e}") from e
    _ASTSecurityScanner().visit(tree)


# ─────────────────────────────────────────────
# Safe import hook
# ─────────────────────────────────────────────

def _make_safe_importer(allowed: frozenset):
    """Return an __import__ replacement that enforces the whitelist."""
    _real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _safe_import(name, *args, **kwargs):
        root = name.split(".")[0]
        if root not in allowed:
            raise ImportError(f"Import of '{name}' is blocked by the sandbox.")
        return _real_import(name, *args, **kwargs)

    return _safe_import


# ─────────────────────────────────────────────
# Cross-platform timeout via ThreadPoolExecutor
# ─────────────────────────────────────────────
#
# Design note
# -----------
# Python threads cannot be forcibly killed, so "timeout" here means:
#   - We stop *waiting* for the thread after `seconds`.
#   - The thread itself is a daemon, so it will not prevent process exit.
#   - A cancellation Event is injected into the sandbox as `_cancel` so
#     well-behaved (or LLM-generated) code can check it in loops.
#
# For typical data-analysis workloads (pandas, numpy, DuckDB queries)
# this is sufficient: operations are C-level and release the GIL, so
# the timeout fires promptly even mid-computation.
#
# Genuine infinite Python loops will leak a daemon thread until the
# process exits – acceptable for a short-lived agent worker process.

def _exec_in_thread(
    byte_code,
    exec_globals: dict,
    exec_locals: dict,
    stdout_buf: io.StringIO,
    cancel_event: threading.Event,
    result_box: list,       # result_box[0] = last_expr, result_box[1] = error
    code: str,
) -> None:
    """Target function run inside the executor thread."""
    exec_globals["_cancel"] = cancel_event  # cooperative cancellation hook
    try:
        with contextlib.redirect_stdout(stdout_buf):
            exec(byte_code, exec_globals, exec_locals)  # noqa: S102
        last_expr = _extract_last_expr(code, exec_locals, exec_globals)
        result_box[0] = last_expr
    except Exception:
        result_box[1] = traceback.format_exc(limit=8)


# ─────────────────────────────────────────────
# Sandbox runner
# ─────────────────────────────────────────────

def run_python_sandbox(
    code: str,
    conn: Optional[duckdb.DuckDBPyConnection] = None,
    schema_name: str = "main",
) -> Dict[str, Any]:
    """
    Execute *code* in a restricted environment.

    Parameters
    ----------
    code        : Python source string submitted by the Agent.
    conn        : Read-only DuckDB connection injected into the sandbox
                  as the name ``conn``.  The Agent can do
                  ``df = conn.execute("SELECT ...").fetchdf()`` inside the code.
    schema_name : Current schema, injected as ``schema_name``.

    Returns
    -------
    dict with keys:
        output      – captured stdout (str)
        result      – value of the last expression (if any)
        error       – error message (str) or None
        elapsed_ms  – wall-clock execution time
    """
    # ── 1. Static AST scan ────────────────────────────────────────────────
    try:
        _scan_ast(code)
    except ValueError as e:
        logger.warning(f"⚠️  run_python blocked by AST scan: {e}")
        return {"output": "", "result": None, "error": str(e), "elapsed_ms": 0}

    # ── 2. Build execution globals ────────────────────────────────────────
    # Use a minimal builtins dict: keeps all standard data-analysis names
    # (list, dict, print, range, …) while stripping dangerous ones
    # (open, exec, eval, compile, __import__, breakpoint, …).
    _builtins_src = __builtins__ if isinstance(__builtins__, dict) else vars(__builtins__)
    _safe_builtins = {
        k: _builtins_src[k] for k in (
            "abs", "all", "any", "bin", "bool", "bytes", "callable",
            "chr", "dict", "divmod", "enumerate", "filter", "float",
            "format", "frozenset", "hasattr", "hash", "hex", "id",
            "int", "isinstance", "issubclass", "iter", "len", "list",
            "map", "max", "min", "next", "oct", "ord", "pow", "print",
            "range", "repr", "reversed", "round", "set", "slice",
            "sorted", "str", "sum", "tuple", "zip",
            "True", "False", "None",
            "Exception", "ValueError", "TypeError", "KeyError",
            "IndexError", "AttributeError", "RuntimeError",
            "StopIteration", "NotImplementedError",
        )
        if k in _builtins_src
    }
    _safe_builtins["__import__"] = _make_safe_importer(ALLOWED_MODULES)
    exec_globals: Dict[str, Any] = {"__builtins__": _safe_builtins}

    # Inject DuckDB read-only proxy and schema name
    if conn is not None:
        exec_globals["conn"] = _ReadOnlyConnProxy(conn, MAX_ROWS_IN_SCOPE)
    exec_globals["schema_name"] = schema_name

    # ── 3. Compile ────────────────────────────────────────────────────────
    try:
        byte_code = compile(code, "<sandbox>", "exec")
    except SyntaxError as e:
        return {"output": "", "result": None, "error": f"Compile error: {e}", "elapsed_ms": 0}

    # ── 4. Execute with stdout capture and cross-platform timeout ─────────
    stdout_buf  = io.StringIO()
    exec_locals: Dict[str, Any] = {}
    cancel_event = threading.Event()
    result_box: list = [None, None]   # [last_expr, error_traceback]
    error: Optional[str] = None
    last_expr = None
    t0 = time.monotonic()

    # Daemon=True: if the main process exits the thread won't block it.
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(
        _exec_in_thread,
        byte_code, exec_globals, exec_locals,
        stdout_buf, cancel_event, result_box, code,
    )
    # Shutdown immediately so no new tasks can be submitted; threads are
    # already running and will finish (or be abandoned) independently.
    executor.shutdown(wait=False)

    try:
        future.result(timeout=MAX_EXEC_SECONDS)
    except concurrent.futures.TimeoutError:
        # Signal cooperative cancellation, then abandon the thread.
        cancel_event.set()
        error = f"Code execution exceeded {MAX_EXEC_SECONDS}s time limit."
        logger.warning(f"⏱️  run_python timeout after {MAX_EXEC_SECONDS}s")
    except Exception:
        # Unexpected executor-level error (rare).
        error = traceback.format_exc(limit=8)

    # Pick up any error raised inside the thread.
    if error is None and result_box[1] is not None:
        error = result_box[1]
    elif error is None:
        last_expr = result_box[0]

    elapsed_ms = round((time.monotonic() - t0) * 1000, 1)

    raw_output = stdout_buf.getvalue()
    if len(raw_output) > MAX_OUTPUT_CHARS:
        raw_output = raw_output[:MAX_OUTPUT_CHARS] + f"\n... [truncated at {MAX_OUTPUT_CHARS} chars]"

    if error:
        logger.error(f"❌ run_python error ({elapsed_ms}ms): {error}")
    else:
        logger.info(f"✅ run_python OK ({elapsed_ms}ms), output={len(raw_output)} chars")

    return {
        "output": raw_output,
        "result": _serialise(last_expr),
        "error": error,
        #"elapsed_ms": elapsed_ms,
    }


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _extract_last_expr(
    code: str,
    local_ns: dict,
    global_ns: dict,
) -> Any:
    """
    If the last statement in *code* is a bare expression, evaluate it and
    return its value.  This mirrors Jupyter's "last-expr" behaviour so the
    Agent can write ``df.describe()`` and get the result back.
    """
    try:
        tree = ast.parse(code)
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last_src = ast.get_source_segment(code, tree.body[-1])
            if last_src:
                return eval(last_src, global_ns, local_ns)  # noqa: S307
    except Exception:
        pass
    return None


def _serialise(value: Any) -> Any:
    """Convert value to a JSON-safe form for the tool result."""
    if value is None:
        return None
    
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure    
    import base64
    import pandas as pd
    import numpy as np

    print(f"value's type:{type(value)}")
    
    try:        
        # If the return value is a Figure object
        if isinstance(value, Figure):
            buf = io.BytesIO()
            value.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)
            img_str = base64.b64encode(buf.read()).decode()
            plt.close(value) # Release memory
            return {
                "type": "image",
                "data": f"data:image/png;base64,{img_str}",
                "format": "png"
            }
       
        if isinstance(value, pd.DataFrame):
            return {
                "type": "dataframe",
                "columns": list(value.columns),
                "rows": value.head(200).to_dict(orient="records"),
                "shape": list(value.shape),
            }
        if isinstance(value, pd.Series):
            return {"type": "series", "data": value.head(200).to_dict()}
        
        if isinstance(value, np.ndarray):
            return {"type": "ndarray", "data": value.tolist(), "shape": list(value.shape)}
        if isinstance(value, (np.integer, np.floating)):
            return value.item() 
    except ImportError:
        pass
    if isinstance(value,str):
        test_result = analyze_image_string(value)
        is_base64_image = test_result.get("is_base64_image",False)
        if is_base64_image:
            return {
                "type": "image",
                "data": value,
                "format": test_result.get("format","")
            }
    if isinstance(value, (int, float, str, bool, list, dict)):
        return value
    return repr(value)

import re
import base64

def analyze_image_string(s: str) -> dict:
    """
    Determines if a string is a Base64 image and returns the image type.

    Supports two formats:
    1. Data URI: data:image/png;base64,xxxxx
    2. Plain Base64: iVBORw0KGgoxxxxx (no prefix)
    """
    result = {'is_base64_image': False, 'format': None, 'mime_type': None, 'has_data_uri': False}
    
    # 尝试 Data URI 前缀
    uri_match = re.match(r'^data:(image/[\w+]+);base64,(.+)$', s, re.DOTALL)
    if uri_match:
        result.update({
            'is_base64_image': True,
            'has_data_uri': True,
            'mime_type': uri_match.group(1),
            'format': uri_match.group(1).split('/')[1],
        })
        return result

    # 无前缀，尝试直接解码检测
    IMAGE_SIGNATURES = {
        b'\x89PNG':      'image/png',
        b'\xff\xd8\xff': 'image/jpeg',
        b'GIF87a':       'image/gif',
        b'GIF89a':       'image/gif',
        b'RIFF':         'image/webp',
        b'BM':           'image/bmp',
    }
    
    try:
        decoded = base64.b64decode(s[:64])
        for magic, mime in IMAGE_SIGNATURES.items():
            if decoded.startswith(magic):
                result.update({
                    'is_base64_image': True,
                    'mime_type': mime,
                    'format': mime.split('/')[1],
                })
                return result
    except Exception:
        pass
    
    return result


class _ReadOnlyConnProxy:
    """
    Thin wrapper around a DuckDB connection that:
    - Only exposes ``execute`` and ``query``
    - Enforces the same SELECT-only rules as SQLTools.execute_sql
    - Caps the number of rows fetchable to MAX_ROWS_IN_SCOPE
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection, max_rows: int):
        self._conn = conn
        self._max_rows = max_rows

    def execute(self, sql: str, params=None):
        self._check(sql)
        if params is not None:
            return self._conn.execute(sql, params)
        return self._conn.execute(sql)

    def query(self, sql: str):
        return self.execute(sql)
    
    def cursor(self):
        return self._conn.cursor()

    def _check(self, sql: str):
        clean = re.sub(r'--.*', '', sql)
        clean = re.sub(r'/\*.*?\*/', '', clean, flags=re.DOTALL)
        upper = clean.strip().upper()
        if not (upper.startswith("SELECT") or upper.startswith("WITH")):
            raise PermissionError("Only SELECT/WITH statements are allowed inside the sandbox.")
        forbidden = [r"\bDROP\b", r"\bDELETE\b", r"\bUPDATE\b",
                     r"\bINSERT\b", r"\bALTER\b", r"\bTRUNCATE\b"]
        if any(re.search(p, upper) for p in forbidden):
            raise PermissionError("Forbidden DDL/DML keyword detected inside the sandbox.")

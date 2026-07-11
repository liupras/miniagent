#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-17
# @description: Convert DB Tool records to LangChain StructuredTools.
#               smart_router type tools are backed by SmartRouter instances.

"""
Tool type conventions (Tool.tool_type)
───────────────────────────────────────
function      Pure Python callable defined in Tool.config["callable_path"]
              Format: "module.submodule:function_name"
api           HTTP endpoint described in Tool.schema / Tool.config
smart_router  Delegates to SmartRouter.query(); requires router_config_id

Tool.schema supports two formats, which _extract_parameters() will automatically recognize:

    Format A — OpenAI function-calling format (the actual format used in the database):
    {
        "type": "function",
            "function": {
            "name": "tool_name",
            "description": "...",
            "parameters": {
            "type": "object",
            "properties": { "query": {...}, "metadata": {...} },
            "required": ["query"]
            }
        }
    }

Format B — Raw JSON Schema (older format, backward compatible):
{
    "type": "object",
    "properties": { ... },
    "required": [...]
}

AgentToolRelation.config_override
              Per-agent JSON that can override any field in Tool.config,
              e.g. {"allowed_kb_ids": [3, 7]} to restrict KB scope for
              a specific agent.
"""

from __future__ import annotations

import importlib
import json
from typing import Any, Dict, List, Optional, Type

import httpx
from langchain_core.tools import StructuredTool, BaseTool
from pydantic import BaseModel, Field, create_model
from loguru import logger
import inspect
from app.infra.db.database import Agent

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

# JSON Schema type → (Python type, default factory)
_JSON_SCHEMA_TYPE_MAP: Dict[str, type] = {
    "string":  str,
    "integer": int,
    "number":  float,
    "boolean": bool,
    "array":   list,
    "object":  dict,
}

def _extract_parameters(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalise Tool.schema to a bare parameters dict with 'properties' and
    'required' keys, regardless of whether the stored schema uses the OpenAI
    function-calling envelope or a raw JSON Schema object.

    OpenAI envelope (Format A):
        {"type": "function", "function": {"parameters": {...}}}
        → returns schema["function"]["parameters"]

    Raw JSON Schema (Format B):
        {"type": "object", "properties": {...}, "required": [...]}
        → returns the dict as-is

    Returns an empty dict if neither format is recognised.
    """
    if not schema:
        return {}

    # Format A：OpenAI function-calling envelope
    if schema.get("type") == "function" and "function" in schema:
        return schema["function"].get("parameters") or {}

    # Format B：Raw JSON Schema (containing properties directly)
    if "properties" in schema:
        return schema

    return {}

def _build_pydantic_model(tool_name: str, schema: Dict[str, Any]) -> Type[BaseModel]:
    """
    Dynamically build a Pydantic v2 model from a JSON Schema dict.

    Only top-level ``properties`` are converted; nested objects become plain
    ``dict``.  This is sufficient for tool-calling schemas.
    """
    parameters = _extract_parameters(schema)
    properties: Dict[str, Any] = parameters.get("properties", {})
    required_fields: List[str] = parameters.get("required", [])

    field_definitions: Dict[str, Any] = {}
    for field_name, field_schema in properties.items():
        py_type = _JSON_SCHEMA_TYPE_MAP.get(field_schema.get("type", "string"), str)
        description = field_schema.get("description", "")

        if field_name in required_fields:
            field_definitions[field_name] = (py_type, Field(..., description=description))
        else:
            # Optional field — use None as default
            default = field_schema.get("default", None)
            field_definitions[field_name] = (
                Optional[py_type],
                Field(default=default, description=description),
            )

    model_name = f"{tool_name.title().replace('_', '')}Input"
    return create_model(model_name, **field_definitions)

def _resolve_callable(callable_path: str):
    """
    Resolve "module.path:function" to a Python callable.

    Raises ImportError / AttributeError on failure so the caller can handle it.
    """
    module_path, func_name = callable_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, func_name)


# ─────────────────────────────────────────────────────────────────────────────
# Per-type builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_function_tool(
        container,
        agent_orm,
        tool_orm, 
        config: Dict[str, Any]) -> BaseTool:
    """
    Build a StructuredTool from a Python callable.

    config keys:
        callable_path   Required. "module:function" string.
        is_async        Optional bool. If True the callable is treated as async.
    """
    callable_path: Optional[str] = config.get("callable_path")
    if not callable_path:
        raise ValueError(
            f"[ToolBuilder] Tool '{tool_orm.name}' (function) "
            "is missing config.callable_path"
        )

    fn = _resolve_callable(callable_path)

    # Factory pattern: If the function accepts an agent parameter, 
    # then the actual coroutine to be generated is passed in.
    if agent_orm is not None and "agent" in inspect.signature(fn).parameters:
        fn = fn(container = container,agent=agent_orm,tool_name=tool_orm.name)

    args_schema = _build_pydantic_model(tool_orm.name, tool_orm.schema or {})
    is_async: bool = config.get("is_async", inspect.iscoroutinefunction(fn))

    return StructuredTool(
        name=tool_orm.name,
        description=tool_orm.description or "",
        args_schema=args_schema,
        func=None if is_async else fn,
        coroutine=fn if is_async else None,
    )

def _build_sql_agent_tool(
        container,
        agent_orm,
        tool_orm, 
        config: Dict[str, Any]) -> BaseTool:
    """
    Build a StructuredTool from a Python callable.

    config keys:
        callable_path   Required. "module:function" string.
        is_async        Optional bool. If True the callable is treated as async.
    """
    callable_path: Optional[str] = config.get("callable_path")
    if not callable_path:
        raise ValueError(
            f"[ToolBuilder] Tool '{tool_orm.name}' (function) "
            "is missing config.callable_path"
        )
    
    schema_name = config.get("schema_name","main")

    fn = _resolve_callable(callable_path)

    # Factory pattern: If the function accepts an agent parameter, 
    # then the actual coroutine to be generated is passed in.
    if agent_orm is not None and "schema_name" in inspect.signature(fn).parameters:
        fn = fn(container = container,agent=agent_orm,tool_name=tool_orm.name,schema_name=schema_name)

    args_schema = _build_pydantic_model(tool_orm.name, tool_orm.schema or {})
    is_async: bool = config.get("is_async", inspect.iscoroutinefunction(fn))

    return StructuredTool(
        name=tool_orm.name,
        description=tool_orm.description or "",
        args_schema=args_schema,
        func=None if is_async else fn,
        coroutine=fn if is_async else None,
    )

def _build_api_tool(tool_orm, config: Dict[str, Any]) -> BaseTool:
    """
    Build an HTTP-based tool.

    config keys:
        url         Required. Endpoint URL. May contain {param} placeholders.
        method      HTTP method (default: POST).
        headers     Optional dict of extra headers.
        timeout     Request timeout in seconds (default: 30).
    """
    url: Optional[str] = config.get("url")
    if not url:
        raise ValueError(
            f"[ToolBuilder] Tool '{tool_orm.name}' (api) is missing config.url"
        )

    method: str = config.get("method", "POST").upper()
    headers: Dict[str, str] = config.get("headers", {})
    timeout: int = config.get("timeout", 30)

    args_schema = _build_pydantic_model(tool_orm.name, tool_orm.schema or {})

    async def _call_api(**kwargs: Any) -> str:
        # Replace URL path placeholders, send remainder as body/params.
        resolved_url = url
        body: Dict[str, Any] = {}
        for key, value in kwargs.items():
            placeholder = f"{{{key}}}"
            if placeholder in resolved_url:
                resolved_url = resolved_url.replace(placeholder, str(value))
            else:
                body[key] = value

        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            if method == "GET":
                resp = await client.get(resolved_url, params=body)
            else:
                resp = await client.request(method, resolved_url, json=body)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "json" in content_type:
                return json.dumps(resp.json(), ensure_ascii=False)
            return resp.text

    return StructuredTool(
        name=tool_orm.name,
        description=tool_orm.description or "",
        args_schema=args_schema,
        coroutine=_call_api,
    )


def _build_smart_router_tool(
    tool_orm,
    config: Dict[str, Any],
    smart_router,           # kb.smart_router.SmartRouter instance
) -> BaseTool:
    """
    Build a knowledge-base retrieval tool backed by a SmartRouter instance.
    """
    base_config: Dict[str, Any] = tool_orm.config or {}
    allowed_kb_ids: Optional[List[int]] = base_config.get("allowed_kb_ids",[])
    max_chunks: int = config.get("max_chunks", 5)
    include_confidence: bool = config.get("include_confidence", True)

    # Dynamically generate args_schema from tool_orm.schema
    args_schema = _build_pydantic_model(tool_orm.name, tool_orm.schema or {})

    # Extract the actual parameter names defined in the schema to correctly route parameters in the coroutine.
    parameters = _extract_parameters(tool_orm.schema or {})
    schema_properties: Dict[str, Any] = parameters.get("properties", {})

    # Identify which field is the main query field (the string type field in the required list).
    required_fields: List[str] = parameters.get("required", [])
    query_field: str = "query"  # default
    for field_name in required_fields:
        field_def = schema_properties.get(field_name, {})
        if field_def.get("type") == "string":
            query_field = field_name
            break

    # The metadata_field was removed here because the metadata_field inferred from LLM is unreliable and can easily cause VectorStore to fail to retrieve results.
    # Find out which field is an optional metadata/filter field (a non-required field of type object).

    logger.debug(
        f"[ToolBuilder] smart_router '{tool_orm.name}': "
        f"query_field='{query_field}', "
        f"allowed_kb_ids={allowed_kb_ids}"
    )

    async def _run_smart_router(**kwargs: Any) -> str:
        """coroutines use **kwargs to receive parameters, without relying on hard-coded signatures."""
        if not allowed_kb_ids:
            return json.dumps(
                {"error": "No knowledge base IDs configured for this tool."},
                ensure_ascii=False,
            )
        
        # Retrieve the query string from kwargs
        query: str = kwargs.get(query_field, "")
        if not query:
            return json.dumps(
                {"error": f"Required field '{query_field}' is missing or empty."},
                ensure_ascii=False,
            )
        
        result = await smart_router.query(
            query=query,
            kb_ids=allowed_kb_ids,
        )

        if result.confidence == "empty" or not result.chunks:
            return json.dumps(
                {
                    "confidence": result.confidence,
                    "warning": result.warning,
                    "chunks": [],
                },
                ensure_ascii=False,
            )

        chunks_out = []
        for chunk in result.chunks[:max_chunks]:
            chunks_out.append(
                {
                    "text": chunk.text,
                    "score": round(float(chunk.final_score), 4),
                    "source": getattr(chunk, "source", None),
                }
            )

        output: Dict[str, Any] = {
            "confidence": result.confidence,
            "chunks": chunks_out,
        }
        if include_confidence and result.warning:
            output["warning"] = result.warning

        return json.dumps(output, ensure_ascii=False)

    return StructuredTool(
        name=tool_orm.name,
        description=tool_orm.description or "Search the knowledge base for relevant information.",
        args_schema=args_schema,
        coroutine=_run_smart_router,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

async def build_tool(
    container,
    agent_orm,
    tool_orm,
    config_override: Optional[Dict[str, Any]],
    router_factory,         # service_container.SmartRouterFactory
) -> Optional[BaseTool]:
    """
    Convert a single Tool ORM instance to a LangChain BaseTool.

    Args:
        tool_orm        ORM row from the ``tool`` table.
        config_override Per-agent config override (from AgentToolRelation).
        router_factory  SmartRouterFactory from ServiceContainer.

    Returns:
        A LangChain BaseTool, or None if the tool is inactive / unsupported.
    """
    if not tool_orm.is_active:
        logger.debug(f"[ToolBuilder] Skipping inactive tool '{tool_orm.name}'")
        return None

    # Merge base config with per-agent override
    base_config: Dict[str, Any] = tool_orm.config or {}
    merged_config: Dict[str, Any] = {**base_config, **(config_override or {})}

    try:
        tool_type: str = tool_orm.tool_type

        if tool_type == "function":
            return _build_function_tool(
                container=container,
                agent_orm=agent_orm,
                tool_orm=tool_orm, 
                config=merged_config
            )
        
        elif tool_type == "sql_agent":
            return _build_sql_agent_tool(
                container=container,
                agent_orm=agent_orm,
                tool_orm=tool_orm, 
                config=merged_config
            )
        
        elif tool_type == "api":
            return _build_api_tool(tool_orm, merged_config)

        elif tool_type == "smart_router":
            router_config_id: Optional[str] = base_config.get("router_config_id","default")
            if not router_config_id:
                raise ValueError(
                    f"Tool '{tool_orm.name}' (smart_router) "
                    "is missing router_config_id"
                )
            smart_router = await router_factory.get_router(router_config_id)
            return _build_smart_router_tool(tool_orm, merged_config, smart_router)

        else:
            logger.warning(
                f"[ToolBuilder] Unknown tool_type='{tool_type}' "
                f"for tool '{tool_orm.name}' — skipping."
            )
            return None

    except Exception as exc:
        logger.error(
            f"[ToolBuilder] Failed to build tool '{tool_orm.name}': {exc}",
            exc_info=True,
        )
        return None


async def build_tools_for_agent(
    container       ,
    agent_orm           :Agent,
    agent_tool_relations: List,     # List[AgentToolRelation ORM rows]
    tool_orm_map        : Dict[str, Any],   # {tool_name: Tool ORM}
    router_factory,
) -> List[BaseTool]:
    """
    Build all LangChain tools for a given agent, preserving priority order.

    Args:
        agent_tool_relations    Rows from agent_tool_relation (already filtered
                                to this agent_id), ordered by priority ASC.
        tool_orm_map            Pre-fetched {tool_name: Tool ORM} lookup dict.
        router_factory          SmartRouterFactory from ServiceContainer.

    Returns:
        List of ready-to-use LangChain tools (inactive/failed ones omitted).
    """
    tools: List[BaseTool] = []

    for relation in agent_tool_relations:
        if not relation.enabled:
            logger.debug(
                f"[ToolBuilder] Tool '{relation.tool_name}' disabled "
                "for this agent — skipping."
            )
            continue

        tool_orm = tool_orm_map.get(relation.tool_name)
        if tool_orm is None:
            logger.warning(
                f"[ToolBuilder] Tool '{relation.tool_name}' not found "
                "in tool_orm_map — skipping."
            )
            continue

        lc_tool = await build_tool(
            container=container,
            agent_orm=agent_orm,
            tool_orm=tool_orm,
            config_override=relation.config_override,
            router_factory=router_factory,
        )
        if lc_tool is not None:
            tools.append(lc_tool)

    logger.info(f"[ToolBuilder] Built {len(tools)} tool(s) for agent.")
    return tools

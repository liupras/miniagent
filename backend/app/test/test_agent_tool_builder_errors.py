import asyncio
from types import SimpleNamespace

import pytest

from app.runtime.agent.tool_builder import (
    ToolBuildError,
    build_tool,
    build_tools_for_agent,
)


def test_inactive_configured_tool_fails_fast():
    tool = SimpleNamespace(
        name="required_tool",
        is_active=False,
        config={},
        tool_type="function",
    )

    with pytest.raises(ToolBuildError, match="inactive"):
        asyncio.run(
            build_tool(
                container=None,
                agent_orm=None,
                tool_orm=tool,
                config_override=None,
                router_factory=None,
            )
        )


def test_missing_related_tool_fails_fast():
    relation = SimpleNamespace(
        tool_name="required_tool",
        config_override=None,
    )

    with pytest.raises(ToolBuildError, match="was not found"):
        asyncio.run(
            build_tools_for_agent(
                container=None,
                agent_orm=None,
                agent_tool_relations=[relation],
                tool_orm_map={},
                router_factory=None,
            )
        )


def test_unsupported_tool_type_fails_fast():
    tool = SimpleNamespace(
        name="required_tool",
        is_active=True,
        config={},
        tool_type="unknown",
    )

    with pytest.raises(ToolBuildError, match="unsupported type"):
        asyncio.run(
            build_tool(
                container=None,
                agent_orm=None,
                tool_orm=tool,
                config_override=None,
                router_factory=None,
            )
        )

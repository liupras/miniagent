import asyncio
from types import SimpleNamespace

import pytest

from app.schemas.exceptions import BaseDomainError, ToolInactiveError
from app.services.skill.web_search.service import WebSearchService
from app.services.sql_agent.service import SQLAgentService


class _ToolDatabase:
    async def get_by_name(self, tool_name):
        return SimpleNamespace(name=tool_name, is_active=False)


@pytest.mark.parametrize(
    ("service_class", "builder_name"),
    [
        (SQLAgentService, "_build_agent"),
        (WebSearchService, "_build_pipeline"),
    ],
)
def test_disabled_tool_raises_shared_domain_error(service_class, builder_name):
    service = object.__new__(service_class)
    service._tool_db = _ToolDatabase()

    with pytest.raises(ToolInactiveError) as caught:
        asyncio.run(getattr(service, builder_name)("disabled_tool"))

    assert isinstance(caught.value, BaseDomainError)
    assert caught.value.tool_name == "disabled_tool"
    assert caught.value.i18n_key() == "tool.inactive"
    assert caught.value.params == {"name": "disabled_tool"}

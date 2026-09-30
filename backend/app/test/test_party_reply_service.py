import asyncio
import json
from pathlib import Path

import pytest

from app.runtime.agent.agent_factory import AgentNotFoundError
from app.runtime.agent.execution import AgentExecution, ToolExecution
from app.runtime.agent.tool_builder import ToolBuildError
from app.runtime.llm.exceptions import ContextBudgetExceeded
from app.schemas.integrations.virtual_court import PartyReplyRequestV1
from app.services.virtual_court import (
    PartyReplyConfigurationError,
    PartyReplyContextError,
    PartyReplyInvalidResponseError,
    PartyReplyService,
    PartyReplyTimeoutError,
)


ROOT = Path(__file__).parent / "fixtures" / "party_reply_v1"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def request():
    data = json.loads(
        (ROOT / "cases/defendant-request.json").read_text(encoding="utf-8")
    )
    return PartyReplyRequestV1.model_validate(data)


class Runner:
    def __init__(self, results, *, delay=0):
        self.results = iter(results)
        self.delay = delay
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        await asyncio.sleep(self.delay)
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


class Factory:
    def __init__(self, runner):
        self.runner = runner
        self.names = []

    async def get_runner_by_name(self, name):
        self.names.append(name)
        if isinstance(self.runner, Exception):
            raise self.runner
        return self.runner


@pytest.mark.anyio
async def test_reply_uses_dedicated_agent_and_trusted_state_version():
    req = request()
    runner = Runner([AgentExecution('{"speech":"没有核验页面展示的授权范围。"}')])
    factory = Factory(runner)

    response = await PartyReplyService(factory).reply(req)

    assert response.state_version == req.state_version
    assert response.speech == "没有核验页面展示的授权范围。"
    assert factory.names == ["virtual_court_party_responder"]
    call = runner.calls[0]
    assert call["history"] is None
    assert call["preserve_context"] is True
    payload = json.loads(call["query"])
    assert "state_version" not in payload
    assert payload["role"] == "DEFENDANT"
    assert payload["question"] == req.question
    assert payload["case_context"]["defenses"] == req.case_context.defenses
    assert payload["records"][0]["text"] == req.records[0].text


@pytest.mark.anyio
async def test_invalid_output_is_repaired_once_and_agent_version_is_rejected():
    runner = Runner(
        [
            AgentExecution('{"state_version":999,"speech":"无效回答"}'),
            AgentExecution('{"speech":"现有记录显示未核验授权范围。"}'),
        ]
    )

    response = await PartyReplyService(Factory(runner)).reply(request())

    assert response.state_version == request().state_version
    assert len(runner.calls) == 2
    assert runner.calls[1]["history"][0] == {
        "role": "user",
        "content": runner.calls[0]["query"],
    }
    assert "schema_validation_failed" in runner.calls[1]["query"]


@pytest.mark.anyio
async def test_invalid_output_is_repaired_only_once():
    runner = Runner([AgentExecution("{}"), AgentExecution("{}")])
    with pytest.raises(PartyReplyInvalidResponseError):
        await PartyReplyService(Factory(runner)).reply(request())
    assert len(runner.calls) == 2


@pytest.mark.anyio
async def test_tool_output_is_rejected():
    tool = ToolExecution(name="search", call_id="1", success=True)
    runner = Runner(
        [
            AgentExecution('{"speech":"错误"}', tools=(tool,)),
            AgentExecution('{"speech":"现有记录中没有核验记录。"}'),
        ]
    )
    response = await PartyReplyService(Factory(runner)).reply(request())
    assert response.speech == "现有记录中没有核验记录。"
    assert "unexpected_tool_call" in runner.calls[1]["query"]


@pytest.mark.anyio
async def test_repair_uses_one_shared_timeout():
    runner = Runner(
        [AgentExecution("{}"), AgentExecution('{"speech":"回答"}')],
        delay=0.035,
    )
    with pytest.raises(PartyReplyTimeoutError):
        await PartyReplyService(
            Factory(runner), timeout_seconds=0.055
        ).reply(request())
    assert len(runner.calls) == 2


@pytest.mark.anyio
async def test_context_overflow_is_not_repaired_or_truncated():
    runner = Runner([ContextBudgetExceeded("overflow")])
    with pytest.raises(PartyReplyContextError):
        await PartyReplyService(Factory(runner)).reply(request())
    assert len(runner.calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error",
    [AgentNotFoundError("missing"), ToolBuildError("bad tool configuration")],
)
async def test_agent_configuration_failures_are_mapped(error):
    with pytest.raises(PartyReplyConfigurationError):
        await PartyReplyService(Factory(error)).reply(request())

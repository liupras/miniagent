"""Transcript generation service behavior with deterministic agent boundaries."""

import asyncio
import json

import pytest

from app.runtime.agent.agent_factory import AgentInactiveError, AgentNotFoundError
from app.runtime.agent.execution import AgentExecution, ToolExecution
from app.runtime.agent.tool_builder import ToolBuildError
from app.runtime.llm.exceptions import ContextBudgetExceeded
from app.runtime.llm.models import LLMClientError
from app.schemas.integrations.virtual_court import TranscriptGenerateRequestV3
from app.services.virtual_court import (
    TranscriptConfigurationError,
    TranscriptContextError,
    TranscriptInvalidResponseError,
    TranscriptService,
    TranscriptTimeoutError,
    TranscriptUnavailableError,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def request(**changes):
    data = {
        "state_version": 42,
        "case_info": {
            "case_id": "case-01", "case_number": "（2026）虚法民初01号",
            "court_name": "虚拟人民法院", "procedure": "民事一审简易程序",
            "cause_of_action": "著作权侵权纠纷", "subject_matter": "《山海鹿鸣》",
            "is_simulated": True, "legal_effect_disclaimer": "模拟案件。",
        },
        "participants": [{
            "participant_id": "judge-01", "role": "judge",
            "display_name": "张某某", "description": "独任审判员",
        }],
        "records": [
            {
                "sequence": 1, "step_id": "OPEN-02", "phase": "court_opening",
                "role": "judge", "text": "现在开庭。", "is_intervention": False,
            },
            {
                "sequence": 2, "step_id": "CLAIM-A", "phase": "claims_and_defence",
                "role": "plaintiff", "text": "请求停止侵权。", "is_intervention": False,
            },
        ],
    }
    data.update(changes)
    return TranscriptGenerateRequestV3.model_validate(data)


def output(first="现在开庭。", second="请求停止侵权。"):
    return json.dumps({"records": [
        {"sequence": 1, "text": first},
        {"sequence": 2, "text": second},
    ]}, ensure_ascii=False)


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
async def test_generate_uses_dedicated_agent_and_complete_material():
    req = request()
    runner = Runner([AgentExecution(output())])
    factory = Factory(runner)

    response = await TranscriptService(factory).generate(req)

    assert response.state_version == req.state_version
    assert [record.sequence for record in response.records] == [1, 2]
    assert factory.names == ["virtual_court_transcript_writer"]
    call = runner.calls[0]
    assert call["history"] is None
    assert call["preserve_context"] is True
    assert "tool_observer" not in call
    assert json.loads(call["query"]) == {"records": [
        {"sequence": 1, "text": "现在开庭。"},
        {"sequence": 2, "text": "请求停止侵权。"},
    ]}
    assert "case_info" not in call["query"]
    assert "participants" not in call["query"]
    assert "state_version" not in call["query"]


@pytest.mark.anyio
async def test_invalid_output_is_repaired_once_with_original_material():
    runner = Runner([AgentExecution("{}"), AgentExecution(output())])
    response = await TranscriptService(Factory(runner)).generate(request())

    assert response.state_version == 42
    assert len(runner.calls) == 2
    assert runner.calls[1]["history"] == [
        {"role": "user", "content": runner.calls[0]["query"]},
        {"role": "assistant", "content": "{}"},
    ]
    assert "schema_validation_failed" in runner.calls[1]["query"]


@pytest.mark.anyio
async def test_invalid_output_is_repaired_at_most_once():
    runner = Runner([AgentExecution("{}"), AgentExecution("{}")])
    with pytest.raises(TranscriptInvalidResponseError):
        await TranscriptService(Factory(runner)).generate(request())
    assert len(runner.calls) == 2


@pytest.mark.anyio
async def test_generation_and_repair_share_one_deadline():
    runner = Runner(
        [AgentExecution("{}"), AgentExecution(output())],
        delay=0.035,
    )
    with pytest.raises(TranscriptTimeoutError):
        await TranscriptService(
            Factory(runner),
            timeout_seconds=0.055,
        ).generate(request())
    assert len(runner.calls) == 2


@pytest.mark.anyio
async def test_agent_cannot_supply_state_version_or_extra_fields():
    invalid = json.dumps(
        {"state_version": 999, "records": []},
        ensure_ascii=False,
    )
    runner = Runner([AgentExecution(invalid), AgentExecution(output())])
    response = await TranscriptService(Factory(runner)).generate(request())
    assert response.state_version == 42
    assert len(runner.calls) == 2


@pytest.mark.anyio
async def test_unexpected_tool_call_is_rejected_and_repaired():
    tool = ToolExecution(name="unexpected", call_id="1", success=True)
    runner = Runner(
        [AgentExecution(output(), (tool,)), AgentExecution(output())]
    )
    response = await TranscriptService(Factory(runner)).generate(request())
    assert response.state_version == 42
    assert len(runner.calls) == 2
    assert "unexpected_tool_call" in runner.calls[1]["query"]


@pytest.mark.anyio
async def test_noncompleted_execution_is_rejected_without_exposing_text():
    runner = Runner(
        [AgentExecution("private partial output", stop_reason="step_limit")]
    )
    with pytest.raises(TranscriptInvalidResponseError) as captured:
        await TranscriptService(Factory(runner)).generate(request())
    assert captured.value.params == {
        "reason": "execution_not_completed",
        "field": "response",
    }
    assert "private" not in str(captured.value.params)


@pytest.mark.anyio
async def test_repair_history_does_not_cross_requests():
    runner = Runner(
        [AgentExecution("{}"), AgentExecution(output()), AgentExecution(output())]
    )
    service = TranscriptService(Factory(runner))
    await service.generate(request())
    await service.generate(request(state_version=43))
    assert runner.calls[2]["history"] is None


@pytest.mark.anyio
async def test_context_overflow_is_not_repaired_or_truncated():
    runner = Runner([ContextBudgetExceeded("overflow")])
    with pytest.raises(TranscriptContextError) as captured:
        await TranscriptService(Factory(runner)).generate(request())
    assert captured.value.params == {
        "reason": "model_context_budget",
        "field": "records",
    }
    assert len(runner.calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error",
    [
        AgentNotFoundError("missing"),
        AgentInactiveError("inactive"),
        ToolBuildError("bad tool configuration"),
    ],
)
async def test_configuration_failures_are_mapped(error):
    with pytest.raises(TranscriptConfigurationError):
        await TranscriptService(Factory(error)).generate(request())


@pytest.mark.anyio
async def test_provider_failure_is_mapped():
    runner = Runner([LLMClientError("unavailable")])
    with pytest.raises(TranscriptUnavailableError):
        await TranscriptService(Factory(runner)).generate(request())

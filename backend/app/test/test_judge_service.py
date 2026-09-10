import asyncio
import json

import pytest

from app.repositories.async_agent import AsyncAgentDatabase
from app.runtime.agent.agent_factory import AgentNotFoundError
from app.runtime.agent.tool_builder import ToolBuildError
from app.runtime.llm.models import LLMClientError
from app.schemas.integrations.virtual_court import JudgeDecisionRequest
from app.services.virtual_court import (
    JudgeConfigurationError,
    JudgeInvalidResponseError,
    JudgeService,
    JudgeTimeoutError,
    JudgeUnavailableError,
)


def _request() -> JudgeDecisionRequest:
    return JudgeDecisionRequest.model_validate(
        {
            "state_version": 18,
            "current_stage": "COURT_INVESTIGATION",
            "current_step": "INQUIRY-D-A",
            "trigger": "CLARIFICATION_NEEDED",
            "task": "要求被告明确回答是否核验过商用授权。",
            "current_speaker": "DEFENDANT",
            "allowed_actions": ["REQUEST_CLARIFICATION"],
            "allowed_targets": ["DEFENDANT"],
            "case_context": {
                "cause_of_action": "著作权侵权纠纷",
                "procedure": "民事一审简易程序",
                "summary": "原告主张被告未经许可使用涉案插画。",
            },
        }
    )


def _valid_output() -> str:
    return json.dumps(
        {
            "issue_assessment": {
                "assessed_issue_id": None,
                "result": "NOT_APPLICABLE",
                "confirmed_facts": [],
                "unresolved_points": [],
                "next_issue_id": None,
            },
            "speech": {
                "type": "CLARIFICATION",
                "text": "被告，请明确回答使用前是否核验过商用授权。",
                "target_role": "DEFENDANT",
            },
            "action": {
                "type": "REQUEST_CLARIFICATION",
                "target_role": "DEFENDANT",
            },
            "legal_citations": [],
            "confidence": "HIGH",
            "warnings": [],
        },
        ensure_ascii=False,
    )


class _FakeRunner:
    def __init__(
        self,
        output: str,
        *,
        error: Exception | None = None,
        delay: float = 0,
        tool_names: frozenset[str] | None = None,
    ) -> None:
        self.output = output
        self.error = error
        self.delay = delay
        self.tool_names = (
            tool_names
            if tool_names is not None
            else frozenset({"intellectual_property_law_search"})
        )
        self.queries: list[str] = []

    async def invoke(self, query: str) -> str:
        self.queries.append(query)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.output


class _FakeAgentFactory:
    def __init__(
        self,
        runner: _FakeRunner,
        *,
        error: Exception | None = None,
    ) -> None:
        self.runner = runner
        self.error = error
        self.names: list[str] = []

    async def get_runner_by_name(self, name: str) -> _FakeRunner:
        self.names.append(name)
        if self.error:
            raise self.error
        return self.runner


def test_agent_repository_supports_factory_name_lookup():
    assert callable(getattr(AsyncAgentDatabase, "get_agent_by_name", None))


@pytest.mark.parametrize(
    ("stage", "agent_name"),
    [
        ("COURT_INVESTIGATION", "virtual_court_investigation_judge"),
        ("COURT_DEBATE", "virtual_court_debate_judge"),
    ],
)
def test_decide_uses_dedicated_agent_and_injects_state_version(stage, agent_name):
    runner = _FakeRunner(_valid_output())
    factory = _FakeAgentFactory(runner)
    service = JudgeService(factory)

    request = JudgeDecisionRequest.model_validate(
        {**_request().model_dump(), "current_stage": stage}
    )
    response = asyncio.run(service.decide(request))

    assert factory.names == [agent_name]
    assert response.state_version == 18
    assert response.action.type.value == "REQUEST_CLARIFICATION"


def test_decide_sends_reasoning_input_and_schema_without_state_version():
    runner = _FakeRunner(_valid_output())
    service = JudgeService(_FakeAgentFactory(runner))

    asyncio.run(service.decide(_request()))

    query = runner.queries[0]
    assert '"current_stage": "COURT_INVESTIGATION"' in query
    assert '"task": "要求被告明确回答是否核验过商用授权。"' in query
    assert '"additionalProperties": false' in query
    payload, schema = query.split("\n\n输出 JSON Schema：\n")
    assert json.loads(payload.removeprefix("庭审输入：\n")) == _request().model_dump(
        mode="json", exclude={"state_version"}
    )
    from app.schemas.integrations.virtual_court import judge_agent_output_json_schema
    assert json.loads(schema) == judge_agent_output_json_schema()
    assert "state_version" not in query


def test_decide_rejects_invalid_agent_output():
    service = JudgeService(_FakeAgentFactory(_FakeRunner("not json")))

    with pytest.raises(JudgeInvalidResponseError) as caught:
        asyncio.run(service.decide(_request()))

    assert caught.value.cause is not None


@pytest.mark.parametrize(
    ("source_error", "expected_error"),
    [
        (AgentNotFoundError("virtual_court_investigation_judge"), JudgeConfigurationError),
        (ToolBuildError("tool failed"), JudgeConfigurationError),
    ],
)
def test_decide_translates_configuration_failures(source_error, expected_error):
    factory = _FakeAgentFactory(_FakeRunner(_valid_output()), error=source_error)

    with pytest.raises(expected_error) as caught:
        asyncio.run(JudgeService(factory).decide(_request()))

    assert caught.value.cause is source_error


def test_decide_translates_llm_failure():
    source_error = LLMClientError("private provider detail")
    runner = _FakeRunner(_valid_output(), error=source_error)

    with pytest.raises(JudgeUnavailableError) as caught:
        asyncio.run(JudgeService(_FakeAgentFactory(runner)).decide(_request()))

    assert caught.value.cause is source_error


def test_decide_rejects_runner_without_required_legal_tool():
    runner = _FakeRunner(_valid_output(), tool_names=frozenset({"other_tool"}))

    with pytest.raises(JudgeConfigurationError) as caught:
        asyncio.run(JudgeService(_FakeAgentFactory(runner)).decide(_request()))
    assert caught.value.params == {
        "reason": "missing_required_tool",
        "tool_name": "intellectual_property_law_search",
    }


def test_decide_enforces_its_own_timeout():
    runner = _FakeRunner(_valid_output(), delay=0.1)
    service = JudgeService(_FakeAgentFactory(runner), timeout_seconds=0.01)

    with pytest.raises(JudgeTimeoutError) as caught:
        asyncio.run(service.decide(_request()))

    assert isinstance(caught.value.cause, TimeoutError)
    assert caught.value.params == {"timeout": 0.01}


def test_consecutive_decisions_only_send_each_requests_context():
    runner = _FakeRunner(_valid_output())
    service = JudgeService(_FakeAgentFactory(runner))
    first = _request()
    second = JudgeDecisionRequest.model_validate(
        {**first.model_dump(), "task": "第二次独立任务", "state_version": 19}
    )

    async def run():
        await service.decide(first)
        return await service.decide(second)

    response = asyncio.run(run())
    assert response.state_version == 19
    assert len(runner.queries) == 2
    assert first.task not in runner.queries[1]
    assert second.task in runner.queries[1]

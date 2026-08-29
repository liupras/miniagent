import asyncio
import json

import pytest

from app.schemas.integrations.virtual_court import JudgeDecisionRequest
from app.services.virtual_court import JudgeOutputValidationError, JudgeService


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
    def __init__(self, output: str) -> None:
        self.output = output
        self.queries: list[str] = []

    async def invoke(self, query: str) -> str:
        self.queries.append(query)
        return self.output


class _FakeAgentFactory:
    def __init__(self, runner: _FakeRunner) -> None:
        self.runner = runner
        self.names: list[str] = []

    async def get_runner_by_name(self, name: str) -> _FakeRunner:
        self.names.append(name)
        return self.runner


def test_decide_uses_dedicated_agent_and_injects_state_version():
    runner = _FakeRunner(_valid_output())
    factory = _FakeAgentFactory(runner)
    service = JudgeService(factory)

    response = asyncio.run(service.decide(_request()))

    assert factory.names == ["virtual_court_solo_judge"]
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
    assert "state_version" not in query


def test_decide_rejects_invalid_agent_output():
    service = JudgeService(_FakeAgentFactory(_FakeRunner("not json")))

    with pytest.raises(JudgeOutputValidationError):
        asyncio.run(service.decide(_request()))

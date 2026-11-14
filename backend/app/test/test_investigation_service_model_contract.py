"""The active investigation service uses the slim model contract end to end."""

import json
from pathlib import Path

import pytest

from app.runtime.agent.execution import AgentExecution
from app.schemas.integrations.virtual_court.investigation import (
    JudgeNextActionRequest,
    ParticipantIntentRequest,
    ParticipantSpeechRequest,
)
from app.services.virtual_court.investigation_model_input import (
    build_intent_model_input,
    build_judge_model_input,
    build_speech_model_input,
)
from app.services.virtual_court.investigation_service import InvestigationAgentService


EXAMPLES = Path(__file__).parent / "fixtures" / "investigation-v4.examples.json"
SEED = Path(__file__).parents[1] / "infra" / "db" / "seed" / "agent.json"


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Runner:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return AgentExecution(next(self.outputs))


class Factory:
    def __init__(self, runner):
        self.runner = runner
        self.names = []

    async def get_runner_by_name(self, name):
        self.names.append(name)
        return self.runner


def _fixture(name):
    return json.loads(EXAMPLES.read_text(encoding="utf-8"))[name]


@pytest.mark.anyio
@pytest.mark.parametrize("operation,fixture_name,request_type,projector,answer", [
    ("intent", "participantIntentRequest", ParticipantIntentRequest,
     build_intent_model_input, {"decision": "pass"}),
    ("speech", "participantSpeechRequest", ParticipantSpeechRequest,
     build_speech_model_input, {"speech": "我方就授权来源作补充说明。"}),
    ("judge", "judgeAgentRequest", JudgeNextActionRequest,
     build_judge_model_input,
     {"decision": "handoff", "reason": "现有记录不足以安全安排下一步。"}),
    ("judge", "judgeAdviceRequest", JudgeNextActionRequest,
     build_judge_model_input,
     {"decision": "action",
      "action": {"type": "reject_request", "requestId": "request_01"},
      "utterance": "本次申请暂不准许。"}),
])
async def test_service_sends_only_projection_and_returns_bound_http_response(
        operation, fixture_name, request_type, projector, answer):
    request = request_type.model_validate(_fixture(fixture_name))
    runner = Runner([json.dumps(answer, ensure_ascii=False)])
    factory = Factory(runner)
    service = InvestigationAgentService(factory)
    result = await getattr(service, {
        "intent": "intent", "speech": "speech", "judge": "next_action",
    }[operation])(request)

    assert factory.names == [service.AGENTS[operation][0]]
    assert len(runner.calls) == 1
    call = runner.calls[0]
    assert call["history"] is None and call["preserve_context"] is True
    assert json.loads(call["query"]) == projector(request)
    assert "investigation_id" not in call["query"]
    assert "decision_revision" not in call["query"]
    assert "turn_id" not in call["query"]
    assert result.investigation_id == request.investigation_id
    if operation == "speech":
        assert result.turn_id == request.turn_id
    else:
        assert result.decision_revision == request.decision_revision
    if operation == "judge":
        assert result.scope == request.scope
        if answer["decision"] == "action":
            assert result.utterance.mode == "text"
            assert result.utterance.text == answer["utterance"]


@pytest.mark.anyio
async def test_service_repairs_missing_decision_using_only_projected_context():
    request = JudgeNextActionRequest.model_validate(_fixture("judgeAgentRequest"))
    runner = Runner([
        json.dumps({"action": {"type": "close_investigation"},
                    "utterance": "调查结束。"}, ensure_ascii=False),
        json.dumps({"decision": "handoff", "reason": "交由人工处理。"}, ensure_ascii=False),
    ])
    result = await InvestigationAgentService(Factory(runner)).next_action(request)
    assert result.decision == "handoff"
    assert len(runner.calls) == 2
    assert '"field": "decision"' in runner.calls[1]["query"]
    assert "具体动作名仅写入 action.type" in runner.calls[1]["query"]
    assert runner.calls[1]["history"][0] == {
        "role": "user", "content": runner.calls[0]["query"],
    }
    assert "investigation_id" not in runner.calls[1]["history"][0]["content"]


def test_three_seed_prompts_match_model_only_contract():
    rows = json.loads(SEED.read_text(encoding="utf-8"))
    prompts = {row["name"]: row["system_prompt"] for row in rows}
    for operation, (name, _, _) in InvestigationAgentService.AGENTS.items():
        prompt = prompts[name]
        assert "只输出" in prompt
        assert "decision_revision" not in prompt
        assert "investigation_id" not in prompt
        assert "turn_id" not in prompt
        assert "displayedEvidenceGroupIds" not in prompt
        if operation == "judge":
            assert "scope=auto" in prompt
            assert "utterance 字符串" in prompt
        if operation == "speech":
            assert '"speech":"本方实际发言"' in prompt

"""Contract and service tests for the three new investigation agents."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.api.exception_handlers import register_global_exception_handlers
from app.api.integrations.errors import register_integration_exception_handlers
from app.api.integrations.virtual_court.investigation import router
from app.core.config import settings
from app.runtime.agent.execution import AgentExecution
from app.schemas.integrations.virtual_court.investigation import (
    JudgeNextActionRequest, JudgeNextActionResponse, ParticipantIntentRequest,
    ParticipantIntentResponse, ParticipantSpeechRequest, ParticipantSpeechResponse,
)
from app.services.virtual_court import (
    InvestigationInvalidResponseError, InvestigationTimeoutError,
)
from app.services.virtual_court.investigation_service import InvestigationAgentService
from app.services.virtual_court.investigation_validator import (
    validate_intent_output, validate_judge_output, validate_speech_output,
)


PREFIX = "/api/v3/integrations/virtual-court"
HEADERS = {"Authorization": "Bearer test-only", "Content-Type": "application/json"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def token(monkeypatch):
    monkeypatch.setattr(settings, "virtual_court_internal_service_token", SecretStr("test-only"))


def base():
    return {
        "investigation_id": "inv_1",
        "case_context": {
            "summary": "图片来源有争议。",
            "participants": [
                {"participantId": "p", "displayName": "请求方"},
                {"participantId": "d", "displayName": "答辩方"},
            ],
            "positions": [{"participantId": "p", "text": "主张未经授权使用。"}],
            "topics": [{"topicId": "t", "text": "授权来源。"}],
            "evidenceGroups": [
                {"evidenceGroupId": "e", "offeringParticipantId": "p",
                 "name": "图片记录", "proofPurpose": "证明使用情况。", "materials": ["网页截图内容。"]}
            ],
        },
        "investigation": {
            "investigationId": "inv_1", "status": "ready", "decisionRevision": 2,
            "currentTopicId": "t", "currentEvidenceGroupId": "e",
            "pendingRequests": [], "activeTurn": None,
        },
        "records": [
            {"sequence": 1, "speakerId": "p", "turnId": "turn_1",
             "kind": "present_evidence", "text": "出示图片记录。",
             "topicId": "t", "evidenceGroupId": "e"}
        ],
    }


def intent_request():
    data = base() | {"decision_revision": 2, "participant_id": "d"}
    return ParticipantIntentRequest.model_validate(data)


def speech_request():
    data = base() | {"turn_id": "turn_2", "participant_id": "d"}
    data["investigation"] = data["investigation"] | {
        "status": "awaiting_speech", "activeTurn": {
            "turnId": "turn_2", "speakerId": "d", "kind": "respond",
            "taskText": "回应图片来源。", "topicId": "t", "evidenceGroupId": "e",
            "replyToTurnId": "turn_1", "targetParticipantId": None,
        },
    }
    return ParticipantSpeechRequest.model_validate(data)


def judge_request():
    data = base() | {"decision_revision": 2}
    data["investigation"] = data["investigation"] | {
        "pendingRequests": [{"requestId": "req_1", "participantId": "d",
                             "speechKind": "respond", "reason": "回应图片来源。",
                             "topicId": "t", "evidenceGroupId": "e",
                             "replyToTurnId": "turn_1"}]
    }
    return JudgeNextActionRequest.model_validate(data)


def test_frozen_shapes_and_reference_validation():
    intent = intent_request()
    response = validate_intent_output(json.dumps({
        "investigation_id": "inv_1", "decision_revision": 2,
        "decision": "request", "speech_kind": "examine_evidence",
        "reason": "质证图片记录。", "topic_id": "t", "evidence_group_id": "e",
        "reply_to_turn_id": None,
    }), intent)
    assert response.speech_kind == "examine_evidence"
    assert validate_speech_output('{"investigation_id":"inv_1","turn_id":"turn_2","speech":"我方回应。"}', speech_request()).turn_id == "turn_2"
    assert validate_judge_output('{"investigation_id":"inv_1","decision_revision":2,"decision":"action","action":{"type":"grant_request","requestId":"req_1"}}', judge_request()).action.requestId == "req_1"
    for raw in (
        '{"investigation_id":"inv_1","decision_revision":2,"decision":"request","speech_kind":"examine_evidence","reason":"质证。","topic_id":"t","evidence_group_id":"invented","reply_to_turn_id":null}',
        '{"investigation_id":"inv_1","decision_revision":2,"decision":"pass","reason":null}',
        '{"investigation_id":"inv_1","decision_revision":2,"decision":"pass","decision":"request"}',
        '{"investigation_id":"other","decision_revision":2,"decision":"pass"}',
    ):
        with pytest.raises(InvestigationInvalidResponseError):
            validate_intent_output(raw, intent)
    with pytest.raises(InvestigationInvalidResponseError):
        validate_judge_output('{"investigation_id":"inv_1","decision_revision":2,"decision":"action","action":{"type":"grant_request","requestId":"invented"}}', judge_request())
    with pytest.raises(InvestigationInvalidResponseError):
        validate_judge_output('{"investigation_id":"inv_1","decision_revision":2,"decision":"action","action":{"type":"close_investigation","text":"总结。"}}', judge_request())
    with pytest.raises(ValidationError):
        ParticipantIntentRequest.model_validate(base() | {"decision_revision": 1, "participant_id": "d"})
    pending = judge_request().model_dump(mode="json")
    pending["participant_id"] = "d"
    duplicate_request = ParticipantIntentRequest.model_validate(pending)
    with pytest.raises(InvestigationInvalidResponseError):
        validate_intent_output(json.dumps({
            "investigation_id": "inv_1", "decision_revision": 2,
            "decision": "request", "speech_kind": "respond",
            "reason": "回应图片来源。", "topic_id": "t", "evidence_group_id": "e",
            "reply_to_turn_id": "turn_1",
        }), duplicate_request)


def test_new_agents_have_separate_prompts_and_no_tools():
    seed = Path(__file__).parents[1] / "infra/db/seed"
    agents = json.loads((seed / "agent.json").read_text(encoding="utf-8"))
    relations = json.loads((seed / "agent_tool_relation.json").read_text(encoding="utf-8"))
    names = {name for name, _ in InvestigationAgentService.AGENTS.values()}
    rows = [item for item in agents if item["name"] in names]
    assert len(rows) == 3
    assert len({item["system_prompt"] for item in rows}) == 3
    assert all(item["is_active"] for item in rows)
    assert not any(item["_agent_name"] in names for item in relations)
    assert {"virtual_court_investigation_judge", "virtual_court_party_responder"} <= {
        item["name"] for item in agents
    }


class Runner:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
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
        return self.runner


@pytest.mark.anyio
async def test_three_distinct_agents_and_one_repair():
    cases = (
        ("intent", intent_request(), '{"investigation_id":"inv_1","decision_revision":2,"decision":"pass"}', "virtual_court_investigation_participant_intent"),
        ("speech", speech_request(), '{"investigation_id":"inv_1","turn_id":"turn_2","speech":"我方回应。"}', "virtual_court_investigation_participant_speech"),
        ("next_action", judge_request(), '{"investigation_id":"inv_1","decision_revision":2,"decision":"action","action":{"type":"grant_request","requestId":"req_1"}}', "virtual_court_investigation_judge_dispatch"),
    )
    for method, request, output, expected_name in cases:
        runner = Runner([AgentExecution("{}"), AgentExecution(output)])
        factory = Factory(runner)
        result = await getattr(InvestigationAgentService(factory), method)(request)
        assert result.investigation_id == "inv_1"
        assert factory.names == [expected_name]
        assert len(runner.calls) == 2
        assert json.loads(runner.calls[0]["query"])["case_context"]["summary"] == "图片来源有争议。"
        assert runner.calls[1]["history"][0]["content"] == runner.calls[0]["query"]


@pytest.mark.anyio
async def test_timeout_does_not_return_pass_or_change_state():
    class SlowRunner:
        async def execute(self, **kwargs):
            await asyncio.sleep(0.05)
            return AgentExecution('{"investigation_id":"inv_1","decision_revision":2,"decision":"pass"}')

    factory = Factory(SlowRunner())
    with pytest.raises(InvestigationTimeoutError):
        await InvestigationAgentService(factory, timeout_seconds=0.001).intent(intent_request())


class Stub:
    async def intent(self, body):
        return ParticipantIntentResponse(investigation_id=body.investigation_id,
                                         decision_revision=body.decision_revision, decision="pass")

    async def speech(self, body):
        return ParticipantSpeechResponse(investigation_id=body.investigation_id,
                                         turn_id=body.turn_id, speech="我方回应。")

    async def next_action(self, body):
        return JudgeNextActionResponse(investigation_id=body.investigation_id,
                                       decision_revision=body.decision_revision,
                                       decision="handoff", reason="需要人工核对。")


def client():
    app = FastAPI()
    app.state.container = SimpleNamespace(investigation_agent_service=Stub())
    app.include_router(router, prefix=PREFIX)
    register_global_exception_handlers(app)
    register_integration_exception_handlers(app)
    return TestClient(app, raise_server_exceptions=False)


def test_http_routes_auth_body_and_response_shapes():
    calls = (
        ("participant/intent", intent_request().model_dump(mode="json"), "pass"),
        ("participant/speech", speech_request().model_dump(mode="json"), None),
        ("judge/next-action", judge_request().model_dump(mode="json"), "handoff"),
    )
    with client() as http:
        for path, body, decision in calls:
            url = PREFIX + "/investigation/" + path
            assert http.post(url, json=body).status_code == 401
            response = http.post(url, headers=HEADERS, json=body)
            assert response.status_code == 200, response.text
            if decision:
                assert response.json()["decision"] == decision
            if decision == "pass":
                assert set(response.json()) == {"investigation_id", "decision_revision", "decision"}
            if decision == "handoff":
                assert "action" not in response.json()
        duplicate = b'{"investigation_id":"inv_1","investigation_id":"inv_1"}'
        response = http.post(PREFIX + "/investigation/participant/intent", headers=HEADERS, content=duplicate)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_REQUEST"
        oversized = b" " * 524289
        response = http.post(PREFIX + "/investigation/participant/intent", headers=HEADERS, content=oversized)
        assert response.status_code == 422
        assert response.json()["error"]["details"]["reason"] == "body_size"

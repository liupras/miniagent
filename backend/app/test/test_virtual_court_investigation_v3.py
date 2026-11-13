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
            "currentTopicId": "t", "currentEvidenceGroupIds": ["e"],
            "pendingRequests": [], "activeTurn": None,
        },
        "records": [
            {"sequence": 1, "speakerId": "p", "turnId": "turn_1",
             "kind": "present_evidence", "text": "出示图片记录。",
             "topicId": "t", "evidenceGroupIds": ["e"],
             "contextEvidenceGroupIds": ["e"]}
        ],
    }


def intent_request():
    data = base() | {"decision_revision": 2, "participant_id": "d"}
    return ParticipantIntentRequest.model_validate(data)


def active_intent_request(status="presenting"):
    data = base() | {"decision_revision": 2, "participant_id": "d"}
    data["investigation"] = data["investigation"] | {
        "status": status,
        "activeTurn": {
            "turnId": "turn_1", "speakerId": "p", "kind": "present_evidence",
            "taskText": "出示图片记录。", "topicId": "t", "evidenceGroupIds": ["e"],
            "contextEvidenceGroupIds": ["e"],
            "replyToTurnId": None, "targetParticipantId": None,
        },
    }
    return data


def speech_request():
    data = base() | {"turn_id": "turn_2", "participant_id": "d"}
    data["investigation"] = data["investigation"] | {
        "status": "awaiting_speech", "activeTurn": {
            "turnId": "turn_2", "speakerId": "d", "kind": "respond",
            "taskText": "回应图片来源。", "topicId": "t", "evidenceGroupIds": ["e"],
            "contextEvidenceGroupIds": ["e"],
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
    pending = judge_request().model_dump(mode="json", exclude_unset=True)
    pending["participant_id"] = "d"
    duplicate_request = ParticipantIntentRequest.model_validate(pending)
    with pytest.raises(InvestigationInvalidResponseError):
        validate_intent_output(json.dumps({
            "investigation_id": "inv_1", "decision_revision": 2,
            "decision": "request", "speech_kind": "respond",
            "reason": "回应图片来源。", "topic_id": "t", "evidence_group_id": "e",
            "reply_to_turn_id": "turn_1",
        }), duplicate_request)


def test_multiple_focused_evidence_and_judge_actions():
    data = base()
    data["case_context"]["evidenceGroups"].append({
        "evidenceGroupId": "e2", "offeringParticipantId": "d",
        "name": "授权记录", "proofPurpose": "说明授权来源。", "materials": ["授权记录正文。"],
    })
    data["investigation"]["currentEvidenceGroupIds"] = ["e", "e2"]
    data["records"][0]["contextEvidenceGroupIds"] = ["e", "e2"]
    request = JudgeNextActionRequest.model_validate(data | {"decision_revision": 2})
    assert request.investigation.currentEvidenceGroupIds == ["e", "e2"]
    assert validate_judge_output(json.dumps({
        "investigation_id": "inv_1", "decision_revision": 2,
        "decision": "action", "action": {
            "type": "set_context", "topicId": "t", "evidenceGroupIds": ["e2"],
        },
    }), request).action.evidenceGroupIds == ["e2"]
    for focus in (["e", "e"], ["missing"], ["e2", "e"]):
        with pytest.raises(InvestigationInvalidResponseError):
            validate_judge_output(json.dumps({
                "investigation_id": "inv_1", "decision_revision": 2,
                "decision": "action", "action": {
                    "type": "set_context", "topicId": "t", "evidenceGroupIds": focus,
                },
            }), request)
    for field in ("currentEvidenceGroupIds", "contextEvidenceGroupIds"):
        malformed = json.loads(json.dumps(data))
        if field == "currentEvidenceGroupIds":
            malformed["investigation"][field] = ["e2", "e"]
        else:
            malformed["records"][0][field] = ["e2", "e"]
        with pytest.raises(ValidationError):
            JudgeNextActionRequest.model_validate(malformed | {"decision_revision": 2})
    with pytest.raises(InvestigationInvalidResponseError):
        validate_judge_output(json.dumps({
            "investigation_id": "inv_1", "decision_revision": 2,
            "decision": "action", "action": {
                "type": "set_context", "topicId": "t", "evidenceGroupId": "e2",
            },
        }), request)


def test_judge_consultation_uses_same_contract_and_agent():
    assert InvestigationAgentService.AGENTS["judge"][0] == "virtual_court_investigation_judge_dispatch"
    request = judge_request().model_dump(mode="json", exclude_unset=True) | {"scope": "request", "request_id": "req_1"}
    selected = JudgeNextActionRequest.model_validate(request)
    advice = validate_judge_output(json.dumps({
        "investigation_id": "inv_1", "decision_revision": 2, "scope": "request",
        "decision": "action", "action": {"type": "grant_request", "requestId": "req_1"},
    }), selected)
    assert advice.action.requestId == "req_1"
    assert validate_judge_output(json.dumps({
        "investigation_id": "inv_1", "decision_revision": 2, "scope": "request",
        "decision": "defer", "reason": "先核对记录。",
    }), selected).decision == "defer"
    for bad in (
        {"scope": "next", "decision": "action", "action": {"type": "grant_request", "requestId": "req_1"}},
        {"scope": "request", "decision": "action", "action": {"type": "grant_request", "requestId": "req_other"}},
        {"scope": "request", "decision": "action", "action": {"type": "close_investigation", "text": "总结。"}},
        {"scope": "next", "decision": "defer", "reason": "稍后。"},
        {"decision": "handoff", "reason": "稍后。"},
    ):
        with pytest.raises(InvestigationInvalidResponseError):
            validate_judge_output(json.dumps({
                "investigation_id": "inv_1", "decision_revision": 2, **bad,
            }), selected)
    with pytest.raises(ValidationError):
        JudgeNextActionRequest.model_validate(request | {"request_id": "missing"})
    with pytest.raises(ValidationError):
        JudgeNextActionRequest.model_validate(request | {"scope": "next"})
    with pytest.raises(InvestigationInvalidResponseError):
        validate_judge_output(json.dumps({
            "investigation_id": "inv_1", "decision_revision": 2, "scope": "request",
            "decision": "handoff", "reason": "稍后。",
        }), judge_request())
    next_request = JudgeNextActionRequest.model_validate(
        judge_request().model_dump(mode="json", exclude_unset=True) | {"scope": "next"}
    )
    assert validate_judge_output(json.dumps({
        "investigation_id": "inv_1", "decision_revision": 2, "scope": "next",
        "decision": "action", "action": {
            "type": "ask_participant", "participantId": "d", "text": "请说明来源。",
            "topicId": "t",
        },
    }), next_request).action.participantId == "d"
    summary = base() | {"decision_revision": 2, "scope": "summary"}
    summary_request = JudgeNextActionRequest.model_validate(summary)
    assert validate_judge_output(json.dumps({
        "investigation_id": "inv_1", "decision_revision": 2, "scope": "summary",
        "decision": "action", "action": {"type": "close_investigation", "text": "双方对来源仍有争议。"},
    }), summary_request).action.type == "close_investigation"
    with pytest.raises(ValidationError):
        JudgeNextActionRequest.model_validate(summary | {"investigation": request["investigation"]})


def test_intent_can_follow_committed_speech_without_taking_the_floor():
    for status in ("presenting", "awaiting_speech"):
        request = ParticipantIntentRequest.model_validate(active_intent_request(status))
        assert request.participant_id == "d"
        assert request.investigation.activeTurn.speakerId == "p"
        assert request.records[-1].turnId == "turn_1"
    with pytest.raises(ValidationError):
        ParticipantIntentRequest.model_validate(active_intent_request() | {"participant_id": "p"})

    question = active_intent_request()
    question["investigation"]["activeTurn"] = {
        "turnId": "turn_2", "speakerId": "judge", "kind": "question",
        "taskText": "请说明图片来源。", "topicId": "t", "evidenceGroupIds": ["e"],
        "contextEvidenceGroupIds": ["e"],
        "replyToTurnId": None, "targetParticipantId": "d",
    }
    question["records"].append({
        "sequence": 2, "speakerId": "judge", "turnId": "turn_2",
        "kind": "question", "text": "请说明图片来源。",
        "topicId": "t", "evidenceGroupIds": ["e"],
        "contextEvidenceGroupIds": ["e"],
    })
    with pytest.raises(ValidationError):
        ParticipantIntentRequest.model_validate(question)
    question["participant_id"] = "p"
    assert ParticipantIntentRequest.model_validate(question).participant_id == "p"

    summary = active_intent_request()
    summary["investigation"]["activeTurn"]["kind"] = "summary"
    with pytest.raises(ValidationError):
        ParticipantIntentRequest.model_validate(summary)
    completed = base() | {"decision_revision": 2, "participant_id": "d"}
    completed["investigation"]["status"] = "completed"
    with pytest.raises(ValidationError):
        ParticipantIntentRequest.model_validate(completed)


def test_new_agents_have_separate_prompts_and_no_tools():
    seed = Path(__file__).parents[1] / "infra/db/seed"
    agents = json.loads((seed / "agent.json").read_text(encoding="utf-8"))
    relations = json.loads((seed / "agent_tool_relation.json").read_text(encoding="utf-8"))
    names = {name for name, _ in InvestigationAgentService.AGENTS.values()}
    rows = [item for item in agents if item["name"] in names]
    assert len(rows) == 3
    assert len({item["system_prompt"] for item in rows}) == 3
    intent_prompt = next(item["system_prompt"] for item in rows if item["name"].endswith("participant_intent"))
    assert "awaiting_speech" in intent_prompt and "presenting" in intent_prompt
    assert "末项是最新已提交的公共发言" in intent_prompt
    assert "currentEvidenceGroupIds" in intent_prompt
    judge_prompt = next(item["system_prompt"] for item in rows if item["name"].endswith("judge_dispatch"))
    assert "scope=request" in judge_prompt and "scope=next" in judge_prompt
    assert "scope=summary" in judge_prompt and "AI 自动主持" in judge_prompt
    assert "set_context(type,topicId,evidenceGroupIds)" in judge_prompt
    assert "contextEvidenceGroupIds" in judge_prompt
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
                                       **({"scope": body.scope} if body.scope else {}),
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
        ("participant/intent", active_intent_request(), "pass"),
        ("participant/speech", speech_request().model_dump(mode="json"), None),
        ("judge/next-action", judge_request().model_dump(mode="json", exclude_unset=True), "handoff"),
        ("judge/next-action", judge_request().model_dump(mode="json", exclude_unset=True) |
         {"scope": "request", "request_id": "req_1"}, "handoff"),
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
                if "scope" in body:
                    assert response.json()["scope"] == body["scope"]
                else:
                    assert "scope" not in response.json()
        duplicate = b'{"investigation_id":"inv_1","investigation_id":"inv_1"}'
        response = http.post(PREFIX + "/investigation/participant/intent", headers=HEADERS, content=duplicate)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_REQUEST"
        oversized = b" " * 524289
        response = http.post(PREFIX + "/investigation/participant/intent", headers=HEADERS, content=oversized)
        assert response.status_code == 422
        assert response.json()["error"]["details"]["reason"] == "body_size"


def test_multi_evidence_turn_and_examination():
    data = base()
    data["case_context"]["evidenceGroups"].append({
        "evidenceGroupId": "e2", "offeringParticipantId": "p",
        "name": "第二组图片记录", "proofPurpose": "证明使用范围。",
        "materials": ["另一页截图。"],
    })
    data["records"][0]["evidenceGroupIds"] = ["e", "e2"]
    data["records"][0]["contextEvidenceGroupIds"] = ["e", "e2"]
    data["investigation"]["currentEvidenceGroupIds"] = ["e", "e2"]
    intent = ParticipantIntentRequest.model_validate(
        data | {"decision_revision": 2, "participant_id": "d"}
    )
    assert validate_intent_output(json.dumps({
        "investigation_id": "inv_1", "decision_revision": 2,
        "decision": "request", "speech_kind": "examine_evidence",
        "reason": "质证第二组证据。", "topic_id": "t",
        "evidence_group_id": "e2", "reply_to_turn_id": None,
    }), intent).evidence_group_id == "e2"
    judge = JudgeNextActionRequest.model_validate(data | {"decision_revision": 2})
    assert validate_judge_output(json.dumps({
        "investigation_id": "inv_1", "decision_revision": 2,
        "decision": "action", "action": {
            "type": "invite_participant", "participantId": "d",
            "speechKind": "examine_evidence", "taskText": "质证两组证据。",
            "topicId": "t", "evidenceGroupIds": ["e", "e2"],
        },
    }), judge).action.evidenceGroupIds == ["e", "e2"]
    bad = json.loads(json.dumps(data))
    bad["records"][0]["evidenceGroupIds"] = ["e2", "e"]
    with pytest.raises(ValidationError):
        JudgeNextActionRequest.model_validate(bad | {"decision_revision": 2})

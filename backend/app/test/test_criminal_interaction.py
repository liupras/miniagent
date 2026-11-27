"""Criminal agents keep room bindings out of the model and validate its choices."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.runtime.agent.execution import AgentExecution
from app.schemas.integrations.virtual_court.criminal_interaction import CriminalInteractionRequest
from app.services.virtual_court.criminal_interaction_service import (
    AGENTS, CriminalInteractionService, model_input,
)
from app.services.virtual_court.exceptions import InvestigationInvalidResponseError


FIXTURE = Path(__file__).parent / "fixtures" / "criminal-ai-v1-request.json"
SEED = Path(__file__).parents[1] / "infra" / "db" / "seed" / "agent.json"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def body(operation, role):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    person = next(item for item in data["casePackage"]["participants"]
                  if item["role"] == role)
    data["operation"] = operation
    data["targetRoleId"] = role
    data["targetParticipantId"] = person["participantId"]
    if operation in {"participant_speech", "witness_speech"}:
        data["interaction"]["status"] = "awaiting_speech"
        data["interaction"]["activeTurn"] = {
            "turnId": "turn-1", "speakerId": person["participantId"],
            "kind": "participant", "speechKind": "statement",
            "topicId": "focus-causal-link",
        }
    return CriminalInteractionRequest.model_validate(data)


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


@pytest.mark.anyio
@pytest.mark.parametrize("operation,role,output", [
    ("intent", "prosecutor", {"decision": "pass"}),
    ("participant_speech", "defense_counsel",
     {"speech": "我方对鉴定意见提出质证意见。",
      "evidenceGroupIds": ["evidence-forensics"]}),
    ("witness_speech", "witness", {"speech": "我只能说明亲眼所见。"}),
    ("judge_action", "judge",
     {"decision": "action", "action": {"type": "invite_participant",
      "participantId": "prosecutor-01", "speechKind": "statement",
      "topicId": "focus-causal-link"}, "utterance": "请公诉人说明。"}),
])
async def test_four_isolated_agents(operation, role, output):
    request = body(operation, role)
    runner = Runner([json.dumps(output, ensure_ascii=False)])
    factory = Factory(runner)
    result = await CriminalInteractionService(factory).run(request)
    assert factory.names == [AGENTS[operation]]
    assert result.callId == request.callId
    assert result.roomEpoch == request.roomEpoch
    assert result.stepRunId == request.stepRunId
    assert result.sourceStateVersion == request.sourceStateVersion
    assert result.result["speech"] == output["speech"] if "speech" in output else True
    projected = json.loads(runner.calls[0]["query"])
    assert projected == model_input(request)
    assert "roomEpoch" not in projected and "caseRevisionId" not in projected
    if operation == "witness_speech":
        assert "charges" not in projected["case"]
        assert len(projected["witnessProfiles"]) == 1


@pytest.mark.anyio
async def test_investigation_summary_uses_record_and_role():
    data = body("participant_speech", "prosecutor").model_dump()
    data["operation"] = "summary_speech"
    data["stepId"] = "investigation_prosecutor_summary"
    data["interaction"]["summaryTask"] = "法庭调查小结"
    request = CriminalInteractionRequest.model_validate(data)
    runner = Runner([json.dumps({"speech": "公诉人依据庭审记录发表小结。",
                                 "evidenceGroupIds": []}, ensure_ascii=False)])
    response = await CriminalInteractionService(Factory(runner)).run(request)
    assert response.operation == "summary_speech"
    assert response.turnId == request.interaction["activeTurn"]["turnId"]
    projected = json.loads(runner.calls[0]["query"])
    assert projected["task"] == "法庭调查小结"
    assert projected["records"] == request.records
    data["stepId"] = "investigation_defense_summary"
    with pytest.raises(ValidationError):
        CriminalInteractionRequest.model_validate(data)


@pytest.mark.anyio
async def test_duplicate_pending_intent_is_treated_as_pass():
    data = body("intent", "defense_counsel").model_dump()
    data["interaction"]["pendingRequests"] = [{
        "requestId": "request-1", "participantId": "defense-01",
        "speechKind": "debate_statement", "topicId": "focus-causal-link",
    }]
    data["interaction"]["mode"] = "criminal_debate"
    request = CriminalInteractionRequest.model_validate(data)
    repeated = {"decision": "request", "speechKind": "debate_statement",
                "topicId": "focus-causal-link"}
    runner = Runner([json.dumps(repeated)])
    response = await CriminalInteractionService(Factory(runner)).run(request)
    assert response.result == {"decision": "pass"}
    assert len(runner.calls) == 1


@pytest.mark.anyio
async def test_unpresented_evidence_is_rejected_after_one_retry():
    request = body("participant_speech", "defense_counsel")
    answer = json.dumps({"speech": "发言。", "evidenceGroupIds": ["evidence-witness"]},
                        ensure_ascii=False)
    runner = Runner([answer, answer])
    with pytest.raises(InvestigationInvalidResponseError):
        await CriminalInteractionService(Factory(runner)).run(request)
    assert len(runner.calls) == 2
    assert ("已出示证据组 " + json.dumps(
        request.interaction["presentedEvidenceGroupIds"], ensure_ascii=False)) in runner.calls[1]["query"]
    assert "删去对未出示具体证据的引用" in runner.calls[1]["query"]


@pytest.mark.anyio
async def test_judge_action_type_in_decision_is_normalized_then_validated():
    request = body("judge_action", "judge")
    answer = {"decision": "invite_participant", "action": {
        "type": "invite_participant", "participantId": "prosecutor-01",
        "speechKind": "statement", "topicId": "focus-causal-link",
    }, "utterance": "请公诉人说明。"}
    runner = Runner([json.dumps(answer, ensure_ascii=False)])
    response = await CriminalInteractionService(Factory(runner)).run(request)
    assert response.result["decision"] == "action"
    assert response.result["action"] == answer["action"]
    assert len(runner.calls) == 1


@pytest.mark.anyio
async def test_judge_invited_accused_response_is_normalized_then_validated():
    request = body("judge_action", "judge")
    answer = {"decision": "invite_participant", "action": {
        "participantId": "accused-01", "speechKind": "answer_accused",
        "topicId": "focus-causal-link",
    }, "utterance": "请被告人说明。"}
    runner = Runner([json.dumps(answer, ensure_ascii=False)])
    response = await CriminalInteractionService(Factory(runner)).run(request)
    assert response.result["decision"] == "action"
    assert response.result["action"]["type"] == "invite_participant"
    assert response.result["action"]["speechKind"] == "statement"
    assert len(runner.calls) == 1


@pytest.mark.anyio
async def test_judge_action_type_mismatch_still_fails():
    request = body("judge_action", "judge")
    answer = {"decision": "grant_request", "action": {
        "type": "invite_participant", "participantId": "prosecutor-01",
        "speechKind": "statement", "topicId": "focus-causal-link",
    }, "utterance": "请公诉人说明。"}
    raw = json.dumps(answer, ensure_ascii=False)
    runner = Runner([raw, raw])
    with pytest.raises(InvestigationInvalidResponseError):
        await CriminalInteractionService(Factory(runner)).run(request)


def test_witness_cannot_speak_in_debate():
    data = body("witness_speech", "witness").model_dump()
    data["interaction"]["mode"] = "criminal_debate"
    with pytest.raises(ValidationError):
        CriminalInteractionRequest.model_validate(data)


def test_kanglei_witness_sees_only_own_statement_material():
    request = body("witness_speech", "witness")
    projected = model_input(request)
    materials = [material for group in projected["case"]["evidenceGroups"]
                 for material in group["materials"]]
    assert {item["materialId"] for item in materials} == {
        "zhanggenbai-statement"}
    assert all(ref["pageStart"] >= 46 and ref["pageEnd"] <= 48
               for item in materials for ref in item["sourceRefs"])
    assert projected["witnessProfiles"][0]["participantId"] == \
        request.targetParticipantId
    assert "charges" not in projected["case"]


def test_four_dedicated_agents_are_seeded():
    prompts = {row["name"]: row["system_prompt"] for row in
               json.loads(SEED.read_text(encoding="utf-8"))}
    assert all(name in prompts for name in AGENTS.values())
    assert "witnessProfiles" in prompts[AGENTS["witness_speech"]]
    assert "sourceRefs 只标注出处页码" in prompts[AGENTS["witness_speech"]]


def test_startup_seed_creates_and_refreshes_four_agents():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.infra.db.database import Agent, Base, LLM
    from app.infra.db.initializer import DatabaseManager

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add_all([
                LLM(name=name, provider_name="test", base_url="http://localhost",
                    model_name=name)
                for name in ("bailian_qwen_plus", "ollama_qwen_4b")
            ])
            db.flush()
            manager = object.__new__(DatabaseManager)
            manager._seed_agent(db, force=False)
            db.flush()
            agents = {agent.name: agent for agent in db.query(Agent).all()
                      if agent.name in AGENTS.values()}
            assert set(agents) == set(AGENTS.values())
            assert all(agent.is_active and agent.llm_id for agent in agents.values())
            agents[AGENTS["witness_speech"]].system_prompt = "stale"
            db.flush()
            manager._seed_agent(db, force=False)
            db.flush()
            assert agents[AGENTS["witness_speech"]].system_prompt != "stale"
    finally:
        engine.dispose()

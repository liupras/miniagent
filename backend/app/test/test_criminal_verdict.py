"""The verdict Agent may cite only the frozen courtroom basis."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.runtime.agent.execution import AgentExecution
from app.schemas.integrations.virtual_court.criminal_verdict import CriminalVerdictRequest
from app.services.virtual_court.criminal_verdict_service import (
    AGENT, CriminalVerdictService,
)
from app.services.virtual_court.exceptions import InvestigationInvalidResponseError


FIXTURE = Path(__file__).parent / "fixtures" / "criminal-ai-v1-request.json"
SEED = Path(__file__).parents[1] / "infra" / "db" / "seed" / "agent.json"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def request_body():
    case = json.loads(FIXTURE.read_text(encoding="utf-8"))["casePackage"]
    accused = next(p for p in case["participants"] if p["role"] == "accused")
    materials = [material for group in case["evidenceGroups"]
                 for material in group["materials"]]
    basis = {
        "caseSummary": case["caseInfo"]["summary"],
        "participants": [{"participantId": p["participantId"],
                          "roleId": p["role"], "displayName": p["displayName"]}
                         for p in case["participants"]],
        "charges": [{key: charge[key] for key in
                     ("chargeId", "crimeName", "allegedFacts", "legalSourceIds")}
                    for charge in case["charges"]],
        "disputeFocuses": [{key: focus[key] for key in ("focusId", "text")}
                           for focus in case["disputeFocuses"]],
        "evidenceMaterials": [
            {"materialId": item["materialId"],
             "displayText": item["displayText"], "usageStatus": "listed",
             "speechSequences": [], "sourceRefs": item["sourceRefs"]}
            for item in materials],
        "legalSources": [{key: law[key] for key in
                          ("legalSourceId", "citation", "text")}
                         for law in case["legalSources"]],
        "records": [{"sequence": 1, "stepId": "accused_final_statement",
                     "participantId": accused["participantId"],
                     "roleId": "accused", "text": "我没有犯法。",
                     "evidenceMaterialIds": []}],
        "lastStatementSequence": 1,
    }
    return {
        "contractVersion": "criminal-verdict-v1",
        "decisionRunId": "run-1", "roomEpoch": "epoch-1",
        "stepRunId": "step-run-1", "caseRevisionId": "revision-1",
        "caseContentSha256": "a" * 64,
        "procedureVersionId": "criminal-first-instance-v1",
        "procedureSha256": "b" * 64, "sourceStateVersion": 12,
        "basisSha256": hashlib.sha256(json.dumps(
            basis, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest(),
        "basis": basis,
    }


def decision(body):
    basis = body["basis"]
    law_id = basis["legalSources"][0]["legalSourceId"]
    return {"status": "decision", "decision": {
        "findings": [{"focusId": item["focusId"],
                      "conclusion": "现有庭审材料不足以确认该事项。",
                      "supportRefs": ["speech:1"], "contraryRefs": []}
                     for item in basis["disputeFocuses"]],
        "chargeDecisions": [{"chargeId": item["chargeId"],
                             "outcome": "acquitted",
                             "reason": "现有材料不足以认定。",
                             "dispositionText": "",
                             "legalSourceIds": [law_id],
                             "basisRefs": ["speech:1", f"legal:{law_id}"]}
                            for item in basis["charges"]],
        "pronouncementText": "本庭模拟训练裁判：现有材料不足以认定。",
    }}


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
async def test_verdict_uses_one_dedicated_agent_and_echoes_bindings():
    body = request_body()
    runner = Runner([json.dumps(decision(body), ensure_ascii=False)])
    factory = Factory(runner)
    response = await CriminalVerdictService(factory).run(
        CriminalVerdictRequest.model_validate(body))
    assert factory.names == [AGENT]
    assert response.decisionRunId == body["decisionRunId"]
    assert response.basisSha256 == body["basisSha256"]
    assert json.loads(runner.calls[0]["query"]) == {"basis": body["basis"]}
    assert "roomEpoch" not in runner.calls[0]["query"]


@pytest.mark.anyio
async def test_unpresented_evidence_is_rejected_after_retry():
    body = request_body()
    output = decision(body)
    output["decision"]["findings"][0]["supportRefs"] = [
        "evidence:" + body["basis"]["evidenceMaterials"][0]["materialId"]]
    raw = json.dumps(output, ensure_ascii=False)
    runner = Runner([raw, raw])
    with pytest.raises(InvestigationInvalidResponseError):
        await CriminalVerdictService(Factory(runner)).run(
            CriminalVerdictRequest.model_validate(body))
    assert len(runner.calls) == 2


@pytest.mark.anyio
async def test_handoff_is_explicit():
    body = request_body()
    runner = Runner(['{"status":"handoff","handoffReason":"材料不足。"}'])
    response = await CriminalVerdictService(Factory(runner)).run(
        CriminalVerdictRequest.model_validate(body))
    assert response.status == "handoff" and response.decision is None


def test_final_statement_must_be_in_frozen_basis():
    body = request_body()
    body["basis"]["records"][0]["stepId"] = "criminal_debate"
    with pytest.raises(ValidationError):
        CriminalVerdictRequest.model_validate(body)


def test_verdict_agent_seeded():
    prompts = {row["name"]: row["system_prompt"] for row in
               json.loads(SEED.read_text(encoding="utf-8"))}
    assert "usageStatus=listed" in prompts[AGENT]


def test_verdict_agent_seed_refreshes_prompt():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.infra.db.database import Agent, Base, LLM
    from app.infra.db.initializer import DatabaseManager

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add(LLM(name="bailian_qwen_plus", provider_name="test",
                       base_url="http://localhost", model_name="test"))
            db.flush()
            manager = object.__new__(DatabaseManager)
            manager._seed_agent(db, force=False)
            db.flush()
            agent = db.query(Agent).filter_by(name=AGENT).one()
            assert agent.is_active and agent.llm_id
            agent.system_prompt = "stale"
            db.flush()
            manager._seed_agent(db, force=False)
            db.flush()
            assert "usageStatus=listed" in agent.system_prompt
    finally:
        engine.dispose()

"""Civil draft API, service, source validation and startup seed checks."""

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.exception_handlers import register_global_exception_handlers
from app.api.integrations.errors import register_integration_exception_handlers
from app.api.integrations.virtual_court.civil_draft import router
from app.core.config import settings
from app.infra.db.database import Agent, AgentToolRelation, Base, LLM
from app.infra.db.initializer import DatabaseManager
from app.runtime.agent.agent_factory import AgentNotFoundError
from app.runtime.agent.execution import AgentExecution
from app.runtime.llm.exceptions import ContextBudgetExceeded
from app.schemas.integrations.virtual_court import (
    CivilCaseDraftGenerateRequestV1,
    CivilCaseDraftGenerateResponseV1,
)
from app.services.virtual_court import (
    CivilDraftConfigurationError,
    CivilDraftContextError,
    CivilDraftInvalidResponseError,
    CivilDraftService,
    CivilDraftTimeoutError,
    CivilDraftUnavailableError,
    validate_civil_draft_agent_output,
)


ENDPOINT = "/api/v2/integrations/virtual-court/cases/civil/draft/generate"
HEADERS = {"Authorization": "Bearer test-only"}
REQUEST = {
    "documents": [
        {"name": "起诉材料.pdf", "text": "【PDF 第1页】\n原告林某请求赔偿经济损失20000元。"},
        {"name": "答辩材料.docx", "text": "被告认为赔偿过高。"},
        {"name": "费用.md", "text": "律师费票据金额6000元。"},
    ],
}
RESPONSE = {
    "draft": {
        "causeOfAction": "著作权侵权纠纷",
        "subjectMatter": "《山海鹿鸣》",
        "summary": "原告请求赔偿，被告对金额有异议。",
        "plaintiff": {"name": "林某", "entityType": "natural_person", "description": ""},
        "defendant": {"name": "", "entityType": None, "description": ""},
        "claims": [{
            "category": "monetary_compensation",
            "text": "赔偿经济损失20000元。",
            "amount": {"totalAmountFen": 2000000, "components": [
                {"name": "经济损失", "amountFen": 2000000}
            ]},
        }],
        "defenses": ["赔偿过高"],
        "disputeFocuses": ["赔偿金额"],
        "evidenceGroups": [{
            "side": "plaintiff",
            "name": "费用摘录",
            "proofPurpose": "证明律师费",
            "materials": [{
                "name": "律师费票据摘录",
                "source": "原告提供",
                "displayText": "律师费票据金额6000元。",
            }],
            "offerSpeech": "原告提交费用摘录。",
            "crossSpeech": "被告请求核对原件。",
        }],
        "fixedSpeeches": {
            "plaintiffClaim": "原告请求赔偿。",
            "defendantAnswer": "被告认为赔偿过高。",
            "plaintiffFocus": "原告坚持赔偿诉请。",
            "defendantFocus": "被告争议赔偿金额。",
            "plaintiffFinal": "请支持诉请。",
            "defendantFinal": "请酌情认定。",
        },
    },
    "issues": [{
        "severity": "blocking",
        "code": "DEFENDANT_NAME_MISSING",
        "message": "答辩材料未写明被告名称。",
    }],
}


@pytest.fixture(autouse=True)
def token(monkeypatch):
    monkeypatch.setattr(settings, "virtual_court_internal_service_token", SecretStr("test-only"))


@pytest.fixture
def anyio_backend():
    return "asyncio"


class ServiceStub:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    async def generate(self, body):
        self.calls.append(body)
        if self.error:
            raise self.error
        return CivilCaseDraftGenerateResponseV1.model_validate(RESPONSE)


def client(service=None):
    app = FastAPI()
    app.state.container = SimpleNamespace(civil_draft_service=service or ServiceStub())
    app.include_router(router, prefix="/api/v2/integrations/virtual-court")
    register_global_exception_handlers(app)
    register_integration_exception_handlers(app)
    return TestClient(app, raise_server_exceptions=False)


def test_http_contract_and_internal_authentication():
    service = ServiceStub()
    assert client(service).post(ENDPOINT, json=REQUEST).status_code == 401
    response = client(service).post(ENDPOINT, headers=HEADERS, json=REQUEST)
    assert response.status_code == 200, response.text
    assert response.json()["issues"][0]["severity"] == "blocking"
    assert len(service.calls) == 1
    assert service.calls[0].documents[2].name == "费用.md"

    invalid = dict(REQUEST, caseId="system-owned")
    assert client(service).post(ENDPOINT, headers=HEADERS, json=invalid).status_code == 422
    assert len(service.calls) == 1


def test_http_rejects_duplicate_json_keys_and_exposes_v1_schema():
    response = client().post(
        ENDPOINT,
        headers=HEADERS,
        content='{"documents":[],"documents":[]}',
    )
    assert response.status_code == 422
    schema = client().get("/openapi.json").json()
    assert set(schema["components"]["schemas"]["CivilCaseDraftGenerateRequestV1"]["properties"]) == {
        "documents"
    }
    assert set(schema["components"]["schemas"]["CivilCaseDraftGenerateResponseV1"]["properties"]) == {
        "draft", "issues"
    }


@pytest.mark.parametrize("error,status,code,retryable", [
    (CivilDraftContextError(), 422, "INVALID_REQUEST", False),
    (CivilDraftConfigurationError(), 503, "SERVICE_UNAVAILABLE", False),
    (CivilDraftUnavailableError(), 503, "SERVICE_UNAVAILABLE", True),
    (CivilDraftTimeoutError(params={"timeout": 300}), 504, "UPSTREAM_TIMEOUT", True),
    (CivilDraftInvalidResponseError(), 502, "MODEL_RESPONSE_INVALID", True),
])
def test_http_error_mapping(error, status, code, retryable):
    response = client(ServiceStub(error)).post(ENDPOINT, headers=HEADERS, json=REQUEST)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["retryable"] is retryable


def test_validator_checks_contract_without_source_refs():
    assert validate_civil_draft_agent_output(json.dumps(RESPONSE, ensure_ascii=False)).draft.claims
    for extra in ({"sourceRefs": []}, {"issues": [{**RESPONSE["issues"][0], "sources": []}]}):
        output = copy.deepcopy(RESPONSE)
        output.update(extra)
        with pytest.raises(CivilDraftInvalidResponseError):
            validate_civil_draft_agent_output(json.dumps(output, ensure_ascii=False))


class Runner:
    def __init__(self, outputs, *, delay=0):
        self.outputs = iter(outputs)
        self.delay = delay
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        await asyncio.sleep(self.delay)
        output = next(self.outputs)
        if isinstance(output, Exception):
            raise output
        return AgentExecution(output)


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
async def test_service_uses_dedicated_agent_and_repairs_once():
    request = CivilCaseDraftGenerateRequestV1.model_validate(REQUEST)
    runner = Runner(["{}", json.dumps(RESPONSE, ensure_ascii=False)])
    factory = Factory(runner)
    result = await CivilDraftService(factory).generate(request)
    assert result.draft.plaintiff.name == "林某"
    assert factory.names == ["virtual_court_civil_draft_generator"]
    assert len(runner.calls) == 2
    assert runner.calls[0]["preserve_context"] is True
    assert json.loads(runner.calls[0]["query"]) == REQUEST
    assert runner.calls[1]["history"][0]["content"] == runner.calls[0]["query"]


@pytest.mark.anyio
async def test_service_timeout_context_and_missing_agent():
    request = CivilCaseDraftGenerateRequestV1.model_validate(REQUEST)
    with pytest.raises(CivilDraftTimeoutError):
        await CivilDraftService(Factory(Runner(["{}", "{}"], delay=0.03)), timeout_seconds=0.045).generate(request)
    with pytest.raises(CivilDraftContextError):
        await CivilDraftService(Factory(Runner([ContextBudgetExceeded("overflow")]))).generate(request)
    with pytest.raises(CivilDraftConfigurationError):
        await CivilDraftService(Factory(AgentNotFoundError("missing"))).generate(request)


def test_seed_adds_agent_without_overwriting_tuned_model():
    rows = json.loads((Path(__file__).parents[1] / "infra/db/seed/agent.json").read_text(encoding="utf-8"))
    row = next(item for item in rows if item["name"] == CivilDraftService.AGENT_NAME)
    assert row["is_active"] is True
    assert "documents 数组" in row["system_prompt"]
    assert "只输出包含 draft 和 issues" in row["system_prompt"]
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            llm = LLM(name="bailian_qwen_plus", provider_name="test", base_url="http://localhost", model_name="test")
            db.add(llm)
            db.flush()
            manager = object.__new__(DatabaseManager)
            manager._seed_agent(db, force=False)
            db.flush()
            agent = db.query(Agent).filter_by(name=CivilDraftService.AGENT_NAME).one()
            assert agent.llm_id == llm.id
            assert db.query(AgentToolRelation).filter_by(agent_id=agent.id).count() == 0
            agent.system_prompt = "outdated"
            manager._seed_agent(db, force=False)
            db.flush()
            assert db.query(Agent).filter_by(name=CivilDraftService.AGENT_NAME).count() == 1
            assert agent.llm_id == llm.id
            assert "只输出包含 draft 和 issues" in agent.system_prompt
            assert "documents 数组" in agent.system_prompt
    finally:
        engine.dispose()

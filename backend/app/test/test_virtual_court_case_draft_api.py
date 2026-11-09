"""Generic case draft API, model repair, authentication and agent seed."""

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
from app.api.integrations.virtual_court.case_draft import router
from app.core.config import settings
from app.infra.db.database import Agent, AgentToolRelation, Base, LLM
from app.infra.db.initializer import DatabaseManager
from app.runtime.agent.agent_factory import AgentNotFoundError
from app.runtime.agent.execution import AgentExecution
from app.runtime.llm.exceptions import ContextBudgetExceeded
from app.schemas.integrations.virtual_court import (
    CaseDraftGenerateRequestV1,
    CaseDraftGenerateResponseV1,
)
from app.services.virtual_court import (
    CaseDraftConfigurationError,
    CaseDraftContextError,
    CaseDraftInvalidResponseError,
    CaseDraftService,
    CaseDraftTimeoutError,
    CaseDraftUnavailableError,
)


ENDPOINT = "/api/v1/integrations/virtual-court/case-drafts/generate"
HEADERS = {"Authorization": "Bearer test-only"}
FIXTURE = json.loads((Path(__file__).parent / "fixtures/case_draft_v1/civil-contract-v1.json").read_text(encoding="utf-8"))
REQUEST, RESPONSE = FIXTURE["request"], FIXTURE["response"]


@pytest.fixture(autouse=True)
def token(monkeypatch):
    monkeypatch.setattr(settings, "virtual_court_internal_service_token", SecretStr("test-only"))


@pytest.fixture
def anyio_backend():
    return "asyncio"


class ServiceStub:
    def __init__(self, error=None, response_data=None):
        self.error = error
        self.response_data = response_data or RESPONSE
        self.calls = []

    async def generate(self, body):
        self.calls.append(body)
        if self.error:
            raise self.error
        return CaseDraftGenerateResponseV1.model_validate(self.response_data)


def client(service=None):
    app = FastAPI()
    app.state.container = SimpleNamespace(case_draft_service=service or ServiceStub())
    app.include_router(router, prefix="/api/v1/integrations/virtual-court")
    register_global_exception_handlers(app)
    register_integration_exception_handlers(app)
    return TestClient(app, raise_server_exceptions=False)


def test_http_contract_and_internal_authentication():
    service = ServiceStub()
    assert client(service).post(ENDPOINT, json=REQUEST).status_code == 401
    response = client(service).post(ENDPOINT, headers=HEADERS, json=REQUEST)
    assert response.status_code == 200, response.text
    assert response.json()["issues"][0]["severity"] == "blocking"
    assert service.calls[0].documents[2].name == "费用.md"
    assert service.calls[0].draftContract.contractId == "civil-case-draft-v1"
    assert client(service).post(ENDPOINT, headers=HEADERS, json=dict(REQUEST, caseId="x")).status_code == 422
    assert len(service.calls) == 1


def test_same_http_route_accepts_another_draft_contract():
    request = copy.deepcopy(REQUEST)
    request["draftContract"] = {
        "contractId": "sample-case-draft-v1",
        "draftSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["finding"],
            "properties": {"finding": {"type": "string", "minLength": 1}},
        },
        "instructions": ["只依据材料归纳 finding。"],
    }
    request["context"] = {"topic": "模拟案件"}
    service = ServiceStub(response_data={"draft": {"finding": "材料显示存在争议。"}, "issues": []})
    response = client(service).post(ENDPOINT, headers=HEADERS, json=request)
    assert response.status_code == 200, response.text
    assert response.json() == {"draft": {"finding": "材料显示存在争议。"}, "issues": []}
    assert service.calls[0].draftContract.contractId == "sample-case-draft-v1"


def test_http_rejects_bad_json_schema_and_oversize_body():
    response = client().post(ENDPOINT, headers=HEADERS, content='{"documents":[],"documents":[]}')
    assert response.status_code == 422
    schema = client().get("/openapi.json").json()
    assert set(schema["components"]["schemas"]["CaseDraftGenerateRequestV1"]["properties"]) == {
        "draftContract", "documents", "context"
    }
    bad = copy.deepcopy(REQUEST)
    bad["draftContract"]["draftSchema"]["properties"]["summary"] = {"$ref": "https://example.com/remote"}
    assert client().post(ENDPOINT, headers=HEADERS, json=bad).status_code == 422
    assert client().post(ENDPOINT, headers=HEADERS, content=b" " * 1_048_577).status_code == 422
    assert not any(route.path.endswith("/cases/civil/draft/generate") for route in router.routes)


@pytest.mark.parametrize("error,status,code,retryable", [
    (CaseDraftContextError(), 422, "INVALID_REQUEST", False),
    (CaseDraftConfigurationError(), 503, "SERVICE_UNAVAILABLE", False),
    (CaseDraftUnavailableError(), 503, "SERVICE_UNAVAILABLE", True),
    (CaseDraftTimeoutError(params={"timeout": 300}), 504, "UPSTREAM_TIMEOUT", True),
    (CaseDraftInvalidResponseError(), 502, "MODEL_RESPONSE_INVALID", True),
])
def test_http_error_mapping(error, status, code, retryable):
    response = client(ServiceStub(error)).post(ENDPOINT, headers=HEADERS, json=REQUEST)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["retryable"] is retryable


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
async def test_service_uses_generic_agent_and_repairs_once():
    request = CaseDraftGenerateRequestV1.model_validate(REQUEST)
    runner = Runner(["{}", json.dumps(RESPONSE, ensure_ascii=False)])
    factory = Factory(runner)
    result = await CaseDraftService(factory).generate(request)
    assert result.draft["plaintiff"]["name"] == "林某"
    assert factory.names == ["virtual_court_case_draft_generator"]
    assert len(runner.calls) == 2
    assert runner.calls[0]["preserve_context"] is True
    assert json.loads(runner.calls[0]["query"]) == REQUEST
    assert runner.calls[1]["history"][0]["content"] == runner.calls[0]["query"]


@pytest.mark.anyio
async def test_service_rejects_output_after_one_failed_repair():
    request = CaseDraftGenerateRequestV1.model_validate(REQUEST)
    runner = Runner(["{}", "{}"])
    with pytest.raises(CaseDraftInvalidResponseError):
        await CaseDraftService(Factory(runner)).generate(request)
    assert len(runner.calls) == 2


@pytest.mark.anyio
async def test_service_timeout_context_and_missing_agent():
    request = CaseDraftGenerateRequestV1.model_validate(REQUEST)
    with pytest.raises(CaseDraftTimeoutError):
        await CaseDraftService(Factory(Runner(["{}", "{}"], delay=0.03)), timeout_seconds=0.045).generate(request)
    with pytest.raises(CaseDraftContextError):
        await CaseDraftService(Factory(Runner([ContextBudgetExceeded("overflow")]))).generate(request)
    with pytest.raises(CaseDraftConfigurationError):
        await CaseDraftService(Factory(AgentNotFoundError("missing"))).generate(request)


def test_seed_adds_generic_agent_without_overwriting_tuned_model():
    rows = json.loads((Path(__file__).parents[1] / "infra/db/seed/agent.json").read_text(encoding="utf-8"))
    row = next(item for item in rows if item["name"] == CaseDraftService.AGENT_NAME)
    assert row["is_active"] is True
    assert "draftContract" in row["system_prompt"]
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
            agent = db.query(Agent).filter_by(name=CaseDraftService.AGENT_NAME).one()
            assert agent.llm_id == llm.id
            assert db.query(AgentToolRelation).filter_by(agent_id=agent.id).count() == 0
            agent.system_prompt = "outdated"
            manager._seed_agent(db, force=False)
            db.flush()
            assert db.query(Agent).filter_by(name=CaseDraftService.AGENT_NAME).count() == 1
            assert agent.llm_id == llm.id
            assert "只输出包含 draft 和 issues" in agent.system_prompt
    finally:
        engine.dispose()

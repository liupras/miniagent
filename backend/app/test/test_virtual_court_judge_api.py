import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.exception_handlers import register_global_exception_handlers
from app.api.integrations.errors import register_integration_exception_handlers
from app.api.integrations.virtual_court.judge import router
from app.core.config import settings
from app.schemas.integrations.virtual_court import (
    JudgeLawCheckResponseV2,
    JudgeNextActionResponseV2,
)
from app.services.virtual_court import (
    JudgeConfigurationError,
    JudgeContextError,
    JudgeInvalidResponseError,
    JudgeTimeoutError,
    JudgeUnavailableError,
)


ROOT = Path(__file__).parent / 'fixtures' / 'judge_v2_split_endpoints'
PREFIX = '/api/v2/integrations/virtual-court'
LAW_ENDPOINT = PREFIX + '/judge/law-check'
NEXT_ENDPOINT = PREFIX + '/judge/next-action'
OLD_ENDPOINT = PREFIX + '/judge/decide'
HEADERS = {'X-Integration-Key': 'test-only', 'Content-Type': 'application/json'}


def load(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


class LawService:
    def __init__(self, error=None):
        self.error = error
        self.requests = []

    async def check(self, body):
        self.requests.append(body)
        if self.error:
            raise self.error
        return JudgeLawCheckResponseV2(
            state_version=body.state_version,
            decision='NO_ACTION',
            speech='',
            pending_points=[],
        )


class NextService:
    def __init__(self, error=None):
        self.error = error
        self.requests = []

    async def decide(self, body):
        self.requests.append(body)
        if self.error:
            raise self.error
        return JudgeNextActionResponseV2(
            state_version=body.state_version,
            decision='HANDOFF',
            target=None,
            speech='请人工处理。',
            pending_points=['待处理事项'],
        )


def client(law_service=None, next_service=None):
    app = FastAPI()
    app.state.container = SimpleNamespace(
        law_check_service=law_service or LawService(),
        next_action_service=next_service or NextService(),
    )
    app.include_router(router, prefix=PREFIX)
    register_global_exception_handlers(app)
    register_integration_exception_handlers(app)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setattr(
        settings,
        'virtual_court_api_key',
        SecretStr('test-only'),
    )


REQUEST_CASES = [
    case
    for case in load('manifest.json')['cases']
    if case['kind'] == 'request'
]


@pytest.mark.parametrize('case', REQUEST_CASES, ids=lambda case: case['id'])
def test_frozen_requests_through_split_http_routes(case):
    law_service = LawService()
    next_service = NextService()
    endpoint = LAW_ENDPOINT if case['endpoint'] == 'law-check' else NEXT_ENDPOINT
    response = client(law_service, next_service).post(
        endpoint,
        headers=HEADERS,
        content=(ROOT / case['file']).read_bytes(),
    )

    assert response.status_code == (200 if case['valid'] else 422), response.text
    service = law_service if case['endpoint'] == 'law-check' else next_service
    assert len(service.requests) == int(case['valid'])
    if not case['valid']:
        assert response.json()['error']['code'] == 'INVALID_REQUEST'


@pytest.mark.parametrize(
    'endpoint, body',
    [
        (LAW_ENDPOINT, load('cases/law-ordinary-request.json')),
        (NEXT_ENDPOINT, load('cases/next-investigation-request.json')),
    ],
)
def test_both_routes_require_integration_key(endpoint, body):
    for headers in ({}, {'X-Integration-Key': 'wrong'}):
        response = client().post(endpoint, headers=headers, json=body)
        assert response.status_code == 401
        assert response.json()['error']['code'] == 'AUTHENTICATION_FAILED'


def test_unconfigured_integration_key_is_503(monkeypatch):
    monkeypatch.setattr(settings, 'virtual_court_api_key', SecretStr(''))
    response = client().post(
        LAW_ENDPOINT,
        headers=HEADERS,
        json=load('cases/law-ordinary-request.json'),
    )
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'SERVICE_UNAVAILABLE'


@pytest.mark.parametrize(
    'error, status, code',
    [
        (
            JudgeInvalidResponseError(
                params={'reason': 'target_not_allowed', 'field': 'target'}
            ),
            502,
            'MODEL_RESPONSE_INVALID',
        ),
        (
            JudgeContextError(
                params={'reason': 'model_context_budget', 'field': 'records'}
            ),
            422,
            'INVALID_REQUEST',
        ),
        (
            JudgeConfigurationError(params={'reason': 'agent_unavailable'}),
            503,
            'SERVICE_UNAVAILABLE',
        ),
        (JudgeUnavailableError(), 503, 'SERVICE_UNAVAILABLE'),
        (JudgeTimeoutError(params={'timeout': 120}), 504, 'UPSTREAM_TIMEOUT'),
    ],
)
@pytest.mark.parametrize('endpoint', [LAW_ENDPOINT, NEXT_ENDPOINT])
def test_split_route_exception_mapping(endpoint, error, status, code):
    body = (
        load('cases/law-ordinary-request.json')
        if endpoint == LAW_ENDPOINT
        else load('cases/next-investigation-request.json')
    )
    response = client(LawService(error), NextService(error)).post(
        endpoint,
        headers=HEADERS,
        json=body,
    )
    assert response.status_code == status
    payload = response.json()['error']
    assert payload['code'] == code
    if error.params.get('reason'):
        assert payload['details']['reason'] == error.params['reason']


def test_old_unified_route_is_deleted():
    response = client().post(OLD_ENDPOINT, headers=HEADERS, json={})
    assert response.status_code == 404


def test_openapi_has_only_split_judge_contracts():
    schema = client().get('/openapi.json').json()
    paths = schema['paths']
    assert LAW_ENDPOINT in paths
    assert NEXT_ENDPOINT in paths
    assert OLD_ENDPOINT not in paths

    components = schema['components']['schemas']
    assert set(components['JudgeLawCheckResponseV2']['properties']) == {
        'state_version', 'decision', 'speech', 'pending_points'
    }
    assert set(components['JudgeNextActionResponseV2']['properties']) == {
        'state_version', 'decision', 'target', 'speech', 'pending_points'
    }


def test_main_registers_virtual_court_router():
    source = (Path(__file__).parents[1] / 'main.py').read_text(encoding='utf-8')
    assert 'prefix="/api/v2/integrations/virtual-court"' in source

    from app.main import app as main_app

    paths = main_app.openapi()['paths']
    assert LAW_ENDPOINT in paths and NEXT_ENDPOINT in paths
    assert OLD_ENDPOINT not in paths


def test_container_registers_only_split_judge_services():
    source = (
        Path(__file__).parents[1] / 'core' / 'service_container.py'
    ).read_text(encoding='utf-8')
    assert 'self.law_check_service = LawCheckService(' in source
    assert 'self.next_action_service = NextActionService(' in source
    assert 'self.judge_service = JudgeService(' not in source


def test_route_logs_are_distinct_and_do_not_log_payloads():
    source = (
        Path(__file__).parents[1]
        / 'api'
        / 'integrations'
        / 'virtual_court'
        / 'judge.py'
    ).read_text(encoding='utf-8')
    assert '[LawCheckV2]' in source and '[NextActionV2]' in source
    assert 'model_dump_json' not in source

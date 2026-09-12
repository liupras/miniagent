import json
from types import SimpleNamespace
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from app.api.integrations.virtual_court.judge import router
from app.api.integrations.errors import register_integration_exception_handlers
from app.api.exception_handlers import register_global_exception_handlers
from app.core.config import settings
from app.schemas.integrations.virtual_court import JudgeDecisionResponse
from app.services.virtual_court import JudgeInvalidResponseError, JudgeContextError
from app.test.judge_v2_helpers import ROOT, load, request_data

ENDPOINT='/api/v2/integrations/virtual-court/judge/decide'
class Service:
    def __init__(self,error=None): self.requests=[]; self.error=error
    async def decide(self,body):
        self.requests.append(body)
        if self.error: raise self.error
        return JudgeDecisionResponse(state_version=body.state_version,decision='HANDOFF',target=None,speech='请人工处理。',pending_points=['待处理'])
def client(service):
    app=FastAPI()
    app.state.container=SimpleNamespace(judge_service=service)
    app.include_router(router,prefix='/api/v2/integrations/virtual-court')
    register_global_exception_handlers(app)
    register_integration_exception_handlers(app)
    return TestClient(app,raise_server_exceptions=False)
@pytest.fixture(autouse=True)
def key(monkeypatch): monkeypatch.setattr(settings,'virtual_court_api_key',SecretStr('test-only'))
HEADERS={'X-Integration-Key':'test-only','Content-Type':'application/json'}
@pytest.mark.parametrize('case',[c for c in load('manifest.json')['cases'] if c['kind']=='request'],ids=lambda c:c['id'])
def test_requests_through_http(case):
    service=Service()
    response=client(service).post(ENDPOINT,headers=HEADERS,content=(ROOT/case['file']).read_bytes())
    assert response.status_code==(200 if case['valid'] else 422),response.text
    assert len(service.requests)==int(case['valid'])
    if not case['valid']: assert response.json()['error']['code']=='INVALID_REQUEST'
def test_auth():
    service=Service()
    for headers in ({},{'X-Integration-Key':'wrong'}):
        res=client(service).post(ENDPOINT,headers=headers,json=request_data())
        assert res.status_code==401
        assert res.json()['error']['code']=='AUTHENTICATION_FAILED'
    assert not service.requests
def test_no_key(monkeypatch):
    monkeypatch.setattr(settings,'virtual_court_api_key',SecretStr(''))
    assert client(Service()).post(ENDPOINT,headers=HEADERS,json=request_data()).status_code==503
@pytest.mark.parametrize('error,status,code',[
    (JudgeInvalidResponseError(params={'reason':'target_not_allowed','field':'target'}),502,'MODEL_RESPONSE_INVALID'),
    (JudgeContextError(params={'reason':'model_context_budget','field':'records'}),422,'INVALID_REQUEST'),
])
def test_diagnostics(error,status,code):
    res=client(Service(error)).post(ENDPOINT,headers=HEADERS,json=request_data())
    assert res.status_code==status
    assert res.json()['error']['code']==code
    assert res.json()['error']['details']['reason']==error.params['reason']
def test_main_registers_judge_endpoint():
    source=(Path(__file__).parents[1]/'main.py').read_text(encoding='utf-8')
    assert 'prefix="/api/v2/integrations/virtual-court"' in source
def test_openapi_exact_response():
    schema=client(Service()).get('/openapi.json').json()
    assert set(schema['components']['schemas']['JudgeDecisionResponse']['properties'])=={'state_version','decision','target','speech','pending_points'}

import asyncio
import json
from types import SimpleNamespace
import pytest
from app.schemas.integrations.virtual_court import JudgeDecisionRequest
from app.services.virtual_court import JudgeService, JudgeInvalidResponseError, JudgeTimeoutError, JudgeContextError
from app.services.virtual_court import JudgeUnavailableError, JudgeConfigurationError
from app.runtime.agent.agent_factory import AgentNotFoundError
from app.runtime.llm.models import LLMClientError
from app.test.judge_v2_helpers import request_data, output
from app.runtime.agent.execution import AgentExecution
from app.runtime.llm.exceptions import ContextBudgetExceeded
from app.services.virtual_court.law_policy import REVISION

@pytest.fixture
def anyio_backend(): return 'asyncio'

class Runner:
    def __init__(self, outputs, delay=0): self.outputs=iter(outputs); self.queries=[]; self.delay=delay
    system_prompt = REVISION
    async def execute(self, **kwargs):
        assert set(kwargs)=={'query','preserve_context','tool_observer'}
        assert kwargs['preserve_context'] is True
        self.queries.append(kwargs['query'])
        await asyncio.sleep(self.delay)
        result=next(self.outputs)
        if isinstance(result,Exception): raise result
        return AgentExecution(result)
class Factory:
    def __init__(self, runner): self.runner=runner; self.names=[]
    async def get_runner_by_name(self,name): self.names.append(name); return self.runner

@pytest.mark.anyio
@pytest.mark.parametrize('phase,name',[('INVESTIGATION','virtual_court_investigation_judge'),('DEBATE','virtual_court_debate_judge')])
async def test_phase_and_server_version(phase,name):
    data=output() if phase=='INVESTIGATION' else {'decision':'COMPLETE','target':None,'speech':'双方意见已归纳。','pending_points':[]}
    runner=Runner([json.dumps(data)])
    factory=Factory(runner)
    req=JudgeDecisionRequest.model_validate(request_data(phase))
    response=await JudgeService(factory).decide(req)
    assert response.state_version==req.state_version
    assert factory.names==[name]
    assert 'state_version' not in runner.queries[0]
    assert 'current_step' not in runner.queries[0]

@pytest.mark.anyio
async def test_one_repair_then_success():
    runner=Runner(['not-json',json.dumps(output())])
    await JudgeService(Factory(runner)).decide(JudgeDecisionRequest.model_validate(request_data()))
    assert len(runner.queries)==2
    assert 'schema_validation_failed' in runner.queries[1]
    assert 'case_context' in runner.queries[1]

@pytest.mark.anyio
async def test_repair_exhausted():
    runner=Runner(['{}','{}',json.dumps(output())])
    with pytest.raises(JudgeInvalidResponseError):
        await JudgeService(Factory(runner)).decide(JudgeDecisionRequest.model_validate(request_data()))
    assert len(runner.queries)==2

@pytest.mark.anyio
async def test_timeout_shared_across_repair():
    runner=Runner(['{}',json.dumps(output())],delay=.035)
    with pytest.raises(JudgeTimeoutError):
        await JudgeService(Factory(runner),timeout_seconds=.055).decide(JudgeDecisionRequest.model_validate(request_data()))
    assert len(runner.queries)==2

@pytest.mark.anyio
async def test_context_overflow_does_not_invoke_or_repair():
    runner=Runner([])
    async def reject(**kwargs): raise ContextBudgetExceeded('overflow')
    runner.execute=reject
    with pytest.raises(JudgeContextError):
        await JudgeService(Factory(runner)).decide(JudgeDecisionRequest.model_validate(request_data()))
    assert not runner.queries

@pytest.mark.anyio
async def test_handoff_is_success_not_retry():
    runner=Runner([json.dumps({'decision':'HANDOFF','target':None,'speech':'请人工处理。','pending_points':['缺少回答']})])
    result=await JudgeService(Factory(runner)).decide(JudgeDecisionRequest.model_validate(request_data()))
    assert result.decision=='HANDOFF' and len(runner.queries)==1

@pytest.mark.anyio
async def test_unavailable_agent_no_retry():
    class Missing:
        async def get_runner_by_name(self,name): raise AgentNotFoundError(name)
    with pytest.raises(JudgeConfigurationError):
        await JudgeService(Missing()).decide(JudgeDecisionRequest.model_validate(request_data()))


@pytest.mark.anyio
async def test_llm_failure_is_not_output_repair():
    runner=Runner([LLMClientError("offline")])
    with pytest.raises(JudgeUnavailableError):
        await JudgeService(Factory(runner)).decide(JudgeDecisionRequest.model_validate(request_data()))
    assert len(runner.queries)==1

@pytest.mark.anyio
async def test_request_permission_error_repaired_once():
    bad={**output(),'target':'WITNESS'}
    runner=Runner([json.dumps(bad),json.dumps(output())])
    await JudgeService(Factory(runner)).decide(JudgeDecisionRequest.model_validate(request_data()))
    assert 'target_not_allowed' in runner.queries[1]

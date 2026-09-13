import asyncio
import json
from pathlib import Path

import pytest

from app.runtime.agent.agent_factory import AgentNotFoundError
from app.runtime.agent.execution import AgentExecution
from app.runtime.agent.tool_builder import ToolBuildError
from app.runtime.llm.exceptions import ContextBudgetExceeded
from app.schemas.integrations.virtual_court import JudgeNextActionRequestV2
from app.services.virtual_court import (
    JudgeConfigurationError,
    JudgeContextError,
    JudgeInvalidResponseError,
    JudgeTimeoutError,
    NextActionService,
)


ROOT = Path(__file__).parent / 'fixtures' / 'judge_v2_split_endpoints'


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def fixture(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def request(phase='INVESTIGATION', **changes):
    filename = (
        'cases/next-investigation-request.json'
        if phase == 'INVESTIGATION'
        else 'cases/next-debate-request.json'
    )
    data = fixture(filename)
    data.update(changes)
    return JudgeNextActionRequestV2.model_validate(data)


def output(decision='COMPLETE', **changes):
    data = {
        'decision': decision,
        'target': 'DEFENDANT' if decision == 'ASK' else None,
        'speech': '请围绕当前事项继续说明。',
        'pending_points': (
            ['尚待说明的事项'] if decision in {'CONTINUE', 'HANDOFF'} else []
        ),
    }
    data.update(changes)
    return json.dumps(data, ensure_ascii=False)


class Runner:
    def __init__(self, results, *, delay=0):
        self.results = iter(results)
        self.delay = delay
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        await asyncio.sleep(self.delay)
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
        if isinstance(self.runner, Exception):
            raise self.runner
        return self.runner


@pytest.mark.anyio
@pytest.mark.parametrize(
    'phase, decision, agent_name',
    [
        ('INVESTIGATION', 'ASK', 'virtual_court_investigation_judge'),
        ('DEBATE', 'CONTINUE', 'virtual_court_debate_judge'),
    ],
)
async def test_phase_routes_to_isolated_flow_agent(phase, decision, agent_name):
    req = request(phase)
    runner = Runner([AgentExecution(output(decision))])
    factory = Factory(runner)
    response = await NextActionService(factory).decide(req)

    assert response.state_version == req.state_version
    assert response.decision == decision
    assert factory.names == [agent_name]
    call = runner.calls[0]
    assert call['history'] is None and call['preserve_context'] is True
    assert json.loads(call['query']) == req.model_dump(
        mode='json', exclude={'state_version'}, exclude_unset=True
    )
    assert 'state_version' not in call['query']
    assert 'records' in call['query']


@pytest.mark.anyio
@pytest.mark.parametrize(
    'phase, forbidden, replacement, reason',
    [
        ('INVESTIGATION', 'CONTINUE', 'ASK', 'decision_not_allowed'),
        ('DEBATE', 'ASK', 'CONTINUE', 'decision_not_allowed'),
        ('INVESTIGATION', 'EXPLAIN_LAW', 'COMPLETE', 'schema_validation_failed'),
        ('DEBATE', 'NO_ACTION', 'COMPLETE', 'schema_validation_failed'),
    ],
)
async def test_cross_phase_and_law_decisions_are_rejected(
    phase, forbidden, replacement, reason
):
    runner = Runner([
        AgentExecution(output(forbidden)),
        AgentExecution(output(replacement)),
    ])
    response = await NextActionService(Factory(runner)).decide(request(phase))
    assert response.decision == replacement
    assert len(runner.calls) == 2
    assert reason in runner.calls[1]['query']


@pytest.mark.anyio
async def test_action_must_be_in_request_allowed_actions():
    req = request(
        'INVESTIGATION',
        allowed_actions=['COMPLETE', 'HANDOFF'],
        allowed_targets=[],
    )
    runner = Runner([
        AgentExecution(output('ASK')),
        AgentExecution(output('COMPLETE')),
    ])
    response = await NextActionService(Factory(runner)).decide(req)
    assert response.decision == 'COMPLETE'
    assert 'decision_not_allowed' in runner.calls[1]['query']


@pytest.mark.anyio
async def test_ask_target_must_be_in_allowed_targets():
    req = request('INVESTIGATION', allowed_targets=['PLAINTIFF'])
    runner = Runner([
        AgentExecution(output('ASK', target='DEFENDANT')),
        AgentExecution(output('ASK', target='PLAINTIFF')),
    ])
    response = await NextActionService(Factory(runner)).decide(req)
    assert response.target == 'PLAINTIFF'
    assert 'target_not_allowed' in runner.calls[1]['query']


@pytest.mark.anyio
async def test_non_ask_target_and_agent_state_version_are_rejected():
    runner = Runner([
        AgentExecution(output('COMPLETE', target='PLAINTIFF', state_version=999)),
        AgentExecution(output('COMPLETE')),
    ])
    response = await NextActionService(Factory(runner)).decide(request())
    assert response.state_version == request().state_version
    assert response.target is None


@pytest.mark.anyio
async def test_invalid_output_repairs_once_under_shared_timeout():
    runner = Runner([
        AgentExecution('{}'),
        AgentExecution(output()),
    ], delay=0.035)
    with pytest.raises(JudgeTimeoutError):
        await NextActionService(
            Factory(runner), timeout_seconds=0.055
        ).decide(request())
    assert len(runner.calls) == 2


@pytest.mark.anyio
async def test_invalid_output_is_repaired_only_once():
    runner = Runner([AgentExecution('{}'), AgentExecution('{}')])
    with pytest.raises(JudgeInvalidResponseError):
        await NextActionService(Factory(runner)).decide(request())
    assert len(runner.calls) == 2
    assert runner.calls[0]['query'] != runner.calls[1]['query']
    assert runner.calls[1]['history'][0] == {
        'role': 'user',
        'content': runner.calls[0]['query'],
    }
    assert 'schema_validation_failed' in runner.calls[1]['query']


@pytest.mark.anyio
async def test_context_overflow_is_not_repaired_or_truncated():
    runner = Runner([ContextBudgetExceeded('overflow')])
    with pytest.raises(JudgeContextError):
        await NextActionService(Factory(runner)).decide(request())
    assert len(runner.calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    'error',
    [AgentNotFoundError('missing'), ToolBuildError('bad tool configuration')],
)
async def test_agent_configuration_failures_are_mapped(error):
    with pytest.raises(JudgeConfigurationError):
        await NextActionService(Factory(error)).decide(request())

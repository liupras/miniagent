import asyncio
import json

import pytest

from app.runtime.agent.execution import AgentExecution, ToolExecution
from app.runtime.agent.tool_builder import ToolBuildError
from app.schemas.integrations.virtual_court import JudgeLawCheckRequestV2
from app.services.virtual_court import (
    JudgeInvalidResponseError,
    JudgeTimeoutError,
    LawCheckService,
)
from app.services.virtual_court.law_policy import LAW_TOOL


@pytest.fixture
def anyio_backend():
    return 'asyncio'


MATERIAL = json.dumps({
    'confidence': 'high',
    'chunks': [{'text': '测试法条及适用条件。'}],
}, ensure_ascii=False)


def request(**changes):
    data = {
        'state_version': 101,
        'role': 'PLAINTIFF',
        'text': '图片公开可下载，为什么不能用于商业宣传？',
        'context': '当前争点：图片商业使用是否构成侵权。',
    }
    data.update(changes)
    return JudgeLawCheckRequestV2.model_validate(data)


def output(decision='NO_ACTION', **changes):
    data = {
        'decision': decision,
        'speech': '' if decision == 'NO_ACTION' else '请依据检索材料处理。',
        'pending_points': ['待人工核对'] if decision == 'HANDOFF' else [],
    }
    data.update(changes)
    return json.dumps(data, ensure_ascii=False)


def tool_execution(*, success=True, body=MATERIAL):
    return ToolExecution(
        name=LAW_TOOL,
        call_id='call-1',
        success=success,
        output=body,
        error=None if success else 'private provider diagnostic',
    )


class Runner:
    def __init__(self, results, *, delay=0, observe=False):
        self.results = iter(results)
        self.delay = delay
        self.observe = observe
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        await asyncio.sleep(self.delay)
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        if self.observe:
            for event in result.tools:
                kwargs['tool_observer'](event)
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
async def test_no_action_uses_isolated_input_and_no_tool():
    runner = Runner([AgentExecution(output())])
    service = LawCheckService(Factory(runner))
    response = await service.check(request(text='我并不是在提出新的法律问题，对吗？'))

    assert response.state_version == 101
    assert response.decision == 'NO_ACTION'
    assert response.speech == '' and response.pending_points == []
    call = runner.calls[0]
    assert call['history'] is None
    assert call['preserve_context'] is True
    assert json.loads(call['query']) == {
        'latest_speech': {
            'role': 'PLAINTIFF',
            'text': '我并不是在提出新的法律问题，对吗？',
        },
        'reference_context': '当前争点：图片商业使用是否构成侵权。',
    }
    assert 'state_version' not in call['query']


@pytest.mark.anyio
async def test_explain_law_requires_current_execution_evidence():
    evidence = tool_execution()
    runner = Runner([AgentExecution(output('EXPLAIN_LAW'), (evidence,))])
    response = await LawCheckService(Factory(runner)).check(request())
    assert response.decision == 'EXPLAIN_LAW'

    runner = Runner([AgentExecution(output('EXPLAIN_LAW'))])
    response = await LawCheckService(Factory(runner)).check(request())
    assert response.decision == 'HANDOFF'
    assert response.pending_points


@pytest.mark.anyio
@pytest.mark.parametrize(
    'event',
    [
        tool_execution(success=False),
        tool_execution(body=json.dumps({'confidence': 'empty', 'chunks': []})),
    ],
)
async def test_failed_or_empty_retrieval_becomes_safe_handoff(event):
    runner = Runner(
        [AgentExecution(output('EXPLAIN_LAW'), (event,))],
        observe=True,
    )
    response = await LawCheckService(Factory(runner)).check(request())
    assert response.decision == 'HANDOFF'
    assert 'private' not in response.model_dump_json()
    assert len(runner.calls) == 1


@pytest.mark.anyio
async def test_no_action_with_tool_call_is_rejected_and_repaired():
    runner = Runner([
        AgentExecution(output(), (tool_execution(),)),
        AgentExecution(output()),
    ])
    response = await LawCheckService(Factory(runner)).check(request())
    assert response.decision == 'NO_ACTION'
    assert len(runner.calls) == 2
    assert runner.calls[0]['query'] != runner.calls[1]['query']
    assert runner.calls[0]['history'] is None
    assert runner.calls[1]['history'][0] == {
        'role': 'user',
        'content': runner.calls[0]['query'],
    }
    assert 'no_action_with_tool_call' in runner.calls[1]['query']


@pytest.mark.anyio
async def test_question_in_context_cannot_trigger_agent_or_tool_for_plain_statement():
    runner = Runner([])
    response = await LawCheckService(Factory(runner)).check(request(
        text='我方维持此前陈述。',
        context='公开下载的图片为何不能商用，法律依据是什么？',
    ))
    assert response.decision == 'NO_ACTION'
    assert runner.calls == []


@pytest.mark.anyio
async def test_invalid_output_repairs_once_under_same_deadline():
    runner = Runner([
        AgentExecution('{}'),
        AgentExecution(output()),
    ], delay=0.035)
    with pytest.raises(JudgeTimeoutError):
        await LawCheckService(Factory(runner), timeout_seconds=0.055).check(request())
    assert len(runner.calls) == 2


@pytest.mark.anyio
async def test_invalid_output_is_repaired_at_most_once():
    runner = Runner([AgentExecution('{}'), AgentExecution('{}')])
    with pytest.raises(JudgeInvalidResponseError):
        await LawCheckService(Factory(runner)).check(request())
    assert len(runner.calls) == 2


@pytest.mark.anyio
async def test_agent_cannot_supply_state_version_or_target():
    invalid = output(state_version=999, target='PLAINTIFF')
    runner = Runner([AgentExecution(invalid), AgentExecution(output())])
    response = await LawCheckService(Factory(runner)).check(request())
    assert response.state_version == 101
    assert len(runner.calls) == 2


@pytest.mark.anyio
async def test_repair_context_and_evidence_do_not_cross_requests():
    runner = Runner([
        AgentExecution('{}'),
        AgentExecution(output()),
        AgentExecution(output('EXPLAIN_LAW')),
    ])
    service = LawCheckService(Factory(runner))
    assert (await service.check(request())).decision == 'NO_ACTION'
    assert (await service.check(request(state_version=102))).decision == 'HANDOFF'
    assert runner.calls[2]['history'] is None


@pytest.mark.anyio
async def test_tool_build_failure_becomes_handoff():
    response = await LawCheckService(Factory(ToolBuildError('private'))).check(request())
    assert response.decision == 'HANDOFF'
    assert 'private' not in response.model_dump_json()

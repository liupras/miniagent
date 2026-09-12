"""Actual AgentLLM/runner/LawCheckService chain with deterministic boundaries."""

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.tools import StructuredTool
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.runtime.agent.agent_runner import AgentRunner
from app.runtime.agent.react_agent import ToolReActAgent
from app.runtime.agent.tool_builder import ToolBuildError
from app.runtime.llm.agent_client import AgentLLM
from app.schemas.integrations.virtual_court import JudgeLawCheckRequestV2
from app.services.virtual_court import (
    JudgeConfigurationError,
    JudgeContextError,
    JudgeTimeoutError,
    LawCheckService,
)
from app.services.virtual_court.law_policy import LAW_TOOL
from app.utils.tokens import TokenCounter


@pytest.fixture
def anyio_backend():
    return 'asyncio'


SOURCE = '测试条文 A（虚构测试资料）：适用条件为测试条件甲。'
MATERIAL = {
    'confidence': 'high',
    'chunks': [{'text': SOURCE, 'citation': {'title': '测试条文 A'}}],
}


def answer(decision='NO_ACTION'):
    return json.dumps({
        'decision': decision,
        'speech': (
            SOURCE
            if decision == 'EXPLAIN_LAW'
            else ('请人工核对适用依据。' if decision == 'HANDOFF' else '')
        ),
        'pending_points': ['依据不足'] if decision == 'HANDOFF' else [],
    }, ensure_ascii=False)


def call(query='请解释适用条件'):
    return {
        'tool_calls': [{
            'id': 'search_1',
            'type': 'function',
            'function': {
                'name': LAW_TOOL,
                'arguments': json.dumps({'query': query}, ensure_ascii=False),
            },
        }]
    }


class Provider:
    max_output_tokens = 2048

    def __init__(self, outputs, delay=0):
        self.outputs = iter(outputs)
        self.messages = []
        self.delay = delay

    async def achat(self, **kwargs):
        self.messages.append(copy.deepcopy(kwargs['messages']))
        await asyncio.sleep(self.delay)
        result = next(self.outputs)
        if isinstance(result, dict):
            return SimpleNamespace(content='', tool_calls=result['tool_calls'])
        return SimpleNamespace(content=result, tool_calls=None)


class Factory:
    def __init__(self, runner):
        self.runner = runner

    async def get_runner_by_name(self, name):
        assert name == LawCheckService.AGENT_NAME
        return self.runner


def setup(
    outputs,
    *,
    material=MATERIAL,
    tool=True,
    tool_delay=0,
    delay=0,
    description='查询法律资料',
):
    calls = []

    async def search(query: str):
        calls.append(query)
        await asyncio.sleep(tool_delay)
        if isinstance(material, Exception):
            raise material
        return json.dumps(material, ensure_ascii=False)

    tools = [
        StructuredTool.from_function(
            coroutine=search,
            name=LAW_TOOL,
            description=description,
        )
    ] if tool else []
    seed_path = (
        Path(__file__).parents[1] / 'infra' / 'db' / 'seed' / 'agent.json'
    )
    seed = json.loads(seed_path.read_text(encoding='utf-8'))
    prompt = next(
        row['system_prompt']
        for row in seed
        if row['name'] == LawCheckService.AGENT_NAME
    )
    provider = Provider(outputs, delay)
    llm = AgentLLM(
        provider,
        'test-model',
        context_window_tokens=32000,
        max_output_tokens=2048,
        token_counter=TokenCounter(
            model='test-model', enable_exact_near_limit=False
        ),
    )
    agent = ToolReActAgent(llm, tools, prompt)
    runner = AgentRunner(
        1,
        LawCheckService.AGENT_NAME,
        agent,
        prompt,
        None,
        SimpleNamespace(
            context_window_tokens=32000,
            max_output_tokens=2048,
            model_name='test-model',
        ),
    )
    request = JudgeLawCheckRequestV2(
        state_version=102,
        role='DEFENDANT',
        text='图片可以公开下载，为什么不能用于商业宣传？法律依据是什么？',
        context='当前争点：涉案图片的商业使用是否构成侵权。',
    )
    return runner, provider, calls, request


@pytest.mark.anyio
async def test_real_tool_trace_and_grounded_context():
    runner, provider, calls, request = setup([call(), answer('EXPLAIN_LAW')])
    result = await LawCheckService(Factory(runner)).check(request)
    assert result.decision == 'EXPLAIN_LAW'
    assert result.speech == SOURCE and result.state_version == request.state_version
    assert len(calls) == 1 and len(provider.messages) == 2
    assert any(
        SOURCE in message['content']
        for message in provider.messages[1]
        if message['role'] == 'tool'
    )
    assert not runner._agent.agent_llm.preserve_context
    user_input = next(
        message['content']
        for message in provider.messages[0]
        if message['role'] == 'user'
    )
    assert 'state_version' not in user_input and 'records' not in user_input


@pytest.mark.anyio
@pytest.mark.parametrize(
    'speech',
    [
        '我方维持此前意见，没有法律问题需要解释。',
        '这难道不是我方一直表达的意见吗？我方没有新的问题。',
    ],
)
async def test_no_action_sends_only_latest_speech_without_search(speech):
    runner, provider, calls, request = setup([answer()])
    request = request.model_copy(update={'text': speech})
    result = await LawCheckService(Factory(runner)).check(request)
    assert result.decision == 'NO_ACTION' and not calls
    assert speech in str(provider.messages[0])


@pytest.mark.anyio
async def test_reference_context_cannot_supply_the_triggering_question():
    runner, provider, calls, request = setup([answer()])
    request = request.model_copy(update={
        'text': '我方维持此前意见。',
        'context': '为什么商业使用公开图片仍可能侵权？',
    })
    result = await LawCheckService(Factory(runner)).check(request)
    assert result.decision == 'NO_ACTION' and not calls


@pytest.mark.anyio
@pytest.mark.parametrize(
    'material',
    [
        {},
        {'error': 'private provider diagnostic'},
        {'confidence': 'empty', 'chunks': []},
        {'chunks': [{'text': '  '}]},
        RuntimeError('private secret'),
        {'chunks': []},
    ],
)
async def test_failed_or_empty_retrieval_handoff(material):
    runner, provider, calls, request = setup(
        [call(), answer('EXPLAIN_LAW')], material=material
    )
    result = await LawCheckService(Factory(runner)).check(request)
    assert result.decision == 'HANDOFF' and result.pending_points
    assert len(provider.messages) == 1 and len(calls) == 1
    assert 'private' not in result.model_dump_json()


@pytest.mark.anyio
async def test_explanation_without_executed_search_handoff():
    runner, provider, calls, request = setup([answer('EXPLAIN_LAW')])
    result = await LawCheckService(Factory(runner)).check(request)
    assert result.decision == 'HANDOFF' and not calls
    assert len(provider.messages) == 1


@pytest.mark.anyio
async def test_missing_tool_still_allows_no_action():
    runner, _, calls, request = setup([answer()], tool=False)
    assert (await LawCheckService(Factory(runner)).check(request)).decision == 'NO_ACTION'
    assert not calls


@pytest.mark.anyio
async def test_tool_build_failure_business_handoff():
    _, _, _, request = setup([])

    class Broken:
        async def get_runner_by_name(self, name):
            raise ToolBuildError('private diagnostic')

    result = await LawCheckService(Broken()).check(request)
    assert result.decision == 'HANDOFF'
    assert 'private' not in result.model_dump_json()


@pytest.mark.anyio
async def test_tool_result_over_budget_is_not_truncated():
    runner, provider, calls, request = setup(
        [call()], material={'chunks': [{'text': '完整资料' * 100000}]}
    )
    with pytest.raises(JudgeContextError):
        await LawCheckService(Factory(runner)).check(request)
    assert len(calls) == 1 and len(provider.messages) == 1


@pytest.mark.anyio
async def test_tool_metadata_over_budget_fails_before_provider():
    runner, provider, calls, request = setup([], description='检索描述' * 100000)
    with pytest.raises(JudgeContextError):
        await LawCheckService(Factory(runner)).check(request)
    assert not calls and not provider.messages


@pytest.mark.anyio
async def test_shared_retrieval_and_repair_deadline():
    runner, _, calls, request = setup(
        [call(), '{}', call(), answer('EXPLAIN_LAW')], tool_delay=0.06
    )
    with pytest.raises(JudgeTimeoutError):
        await LawCheckService(
            Factory(runner), timeout_seconds=0.10
        ).check(request)
    assert len(calls) == 2


@pytest.mark.anyio
async def test_repair_retrieves_again_and_keeps_isolated_request():
    runner, provider, calls, request = setup(
        [call(), '{}', call(), answer('EXPLAIN_LAW')]
    )
    result = await LawCheckService(Factory(runner)).check(request)
    assert result.decision == 'EXPLAIN_LAW' and len(calls) == 2
    assert 'schema_validation_failed' in str(provider.messages[2])
    assert 'records' not in str(provider.messages[2])


@pytest.mark.anyio
async def test_cached_runner_does_not_reuse_previous_evidence():
    runner, _, calls, request = setup([
        call(),
        answer('EXPLAIN_LAW'),
        answer('EXPLAIN_LAW'),
    ])
    service = LawCheckService(Factory(runner))
    assert (await service.check(request)).decision == 'EXPLAIN_LAW'
    assert (await service.check(request)).decision == 'HANDOFF'
    assert len(calls) == 1


def test_law_check_agent_seed_keeps_runtime_parameters():
    from app.infra.db.database import Agent, Base, LLM, Tool
    from app.infra.db.initializer import DatabaseManager

    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            llm = LLM(
                name='tuned',
                provider_name='test',
                base_url='http://localhost',
                model_name='tuned',
                temperature=0.23,
            )
            law = Tool(name=LAW_TOOL, tool_schema={})
            db.add_all([llm, law])
            db.flush()
            agent = Agent(
                name=LawCheckService.AGENT_NAME,
                system_prompt='已有人工提示词',
                llm_id=llm.id,
                max_output_tokens=3000,
            )
            db.add(agent)
            db.flush()
            manager = object.__new__(DatabaseManager)
            manager._seed_agent(db, force=False)
            db.flush()
            assert agent.system_prompt == '已有人工提示词'
            assert agent.max_output_tokens == 3000 and agent.llm_id == llm.id
            assert llm.temperature == 0.23
    finally:
        engine.dispose()


def test_prompt_without_version_marker_is_accepted():
    runner, _, _, _ = setup([])
    assert '[JudgeAPI V2:' not in runner.system_prompt

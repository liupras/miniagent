"""Generic execution policy, trace isolation and configured smart-router integration."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest
from app.runtime.agent.agent_runner import AgentRunner
from app.runtime.agent.agent_factory import AgentFactory
from app.runtime.agent.react_agent import ToolReActAgent
from app.runtime.agent.execution import AgentExecution
from app.runtime.llm.agent_client import AgentLLM
from app.runtime.llm.exceptions import ContextBudgetExceeded
from app.runtime.agent.exceptions import ToolExecutionError
from app.test.test_judge_legal_execution import setup, call, answer, MATERIAL, SOURCE

@pytest.fixture
def anyio_backend():return 'asyncio'

@pytest.mark.anyio
async def test_generic_result_contains_trace_without_judge_decisions():
    runner,provider,calls,_=setup([call(),'plain final text'])
    result=await runner.execute('ordinary question',preserve_context=True)
    assert result.text=='plain final text' and result.stop_reason=='completed'
    assert len(result.tools)==1 and result.tools[0].success
    assert result.tools[0].call_id=='search_1' and SOURCE in result.tools[0].output
    assert SOURCE not in repr(result) and SOURCE not in repr(result.tools[0])

@pytest.mark.anyio
async def test_generic_execution_does_not_apply_law_failure_policy():
    runner,provider,calls,_=setup([call(),'No source found'],material={'chunks':[]})
    result=await runner.execute('question',preserve_context=True)
    assert result.text=='No source found' and result.tools[0].success
    assert len(provider.messages)==2

@pytest.mark.anyio
async def test_failure_observation_does_not_swallow_existing_error():
    runner,_,_,_=setup([call()],material=RuntimeError('private detail'))
    events=[]
    with pytest.raises(ToolExecutionError):
        await runner.execute('question',preserve_context=True,tool_observer=events.append)
    assert len(events)==1 and not events[0].success
    assert events[0].error=='execution_failed' and 'private' not in repr(events)

@pytest.mark.anyio
async def test_observer_can_stop_before_next_model_request():
    runner,provider,calls,_=setup([call()])
    class Stop(Exception):pass
    def stop(event):raise Stop()
    with pytest.raises(Stop):await runner.execute('question',preserve_context=True,tool_observer=stop)
    assert len(provider.messages)==1 and len(calls)==1

@pytest.mark.anyio
async def test_context_overflow_is_generic_and_prevents_model_call():
    runner,provider,calls,_=setup([])
    with pytest.raises(ContextBudgetExceeded):await runner.execute('内容'*40000,preserve_context=True)
    assert not provider.messages and not calls

@pytest.mark.anyio
async def test_preserve_context_keeps_explicit_history_without_database():
    runner,provider,_,_=setup(['ok'])
    history=[{'role':'user','content':'earlier question'},{'role':'assistant','content':'earlier answer'}]
    result=await runner.execute('latest',history,preserve_context=True)
    assert result.text=='ok'
    assert provider.messages[0][-3:]==history+[{'role':'user','content':'latest'}]
    assert len(history)==2
    with pytest.raises(ValueError):await runner.execute('latest',user_id='u',preserve_context=True)

@pytest.mark.anyio
async def test_legacy_invoke_keeps_string_return_and_persistence():
    runner,_,_,_=setup(['plain answer'])
    conversation=SimpleNamespace(build_messages=AsyncMock(return_value=[{'role':'user','content':'question'}]),save_message=AsyncMock())
    runner._conversation_service=conversation
    value=await runner.invoke('question',user_id='u',session_id=4)
    assert value=='plain answer'
    assert [c.kwargs['role'] for c in conversation.save_message.await_args_list]==['user','assistant']
    assert conversation.build_messages.await_args.kwargs['session_id']==4
    assert runner._agent.agent_llm.preserve_context is False

@pytest.mark.anyio
async def test_trace_is_local_to_each_execution():
    runner,_,_,_=setup([call(),'one','two'])
    first=await runner.execute('first',preserve_context=True)
    second=await runner.execute('second',preserve_context=True)
    assert len(first.tools)==1 and not second.tools

@pytest.mark.anyio
async def test_concurrent_policies_do_not_mutate_cached_llm():
    runner,_,_,_=setup([])
    class LLM:
        preserve_context=False
        async def achat(self,messages,tool_schema=None):
            await asyncio.sleep(.01)
            return {'role':'assistant','content':str(self.preserve_context)}
    runner._agent.agent_llm=LLM()
    runner._conversation_service=SimpleNamespace(build_messages=AsyncMock(return_value=[{'role':'user','content':'x'}]))
    strict,normal=await asyncio.gather(runner.execute('x',preserve_context=True),runner.execute('x'))
    assert strict.text=='True' and normal.text=='False'
    assert runner._agent.agent_llm.preserve_context is False

@pytest.mark.anyio
async def test_step_limit_is_distinct_from_completed():
    runner,_,calls,_=setup([call() for _ in range(10)])
    result=await runner.execute('x',preserve_context=True)
    assert result.stop_reason=='step_limit' and len(calls)==10

@pytest.mark.anyio
async def test_cancellation_is_not_a_tool_failure():
    runner,_,_,_=setup([call()],tool_delay=.2)
    events=[]
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(.04):await runner.execute('x',preserve_context=True,tool_observer=events.append)
    assert not events

@pytest.mark.anyio
@pytest.mark.parametrize('phase',['INVESTIGATION','DEBATE'])
async def test_database_config_to_factory_smart_router_and_judge(monkeypatch,phase):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.infra.db.database import Base,Agent,Tool,LLM,AgentToolRelation
    from app.runtime.llm.client import LLMClient
    import app.core.prompt_loader as prompt_module
    monkeypatch.setattr(prompt_module, 'prompt_loader', SimpleNamespace(get=lambda key: ''))
    from app.services.virtual_court import JudgeService
    from app.test.test_judge_legal_execution import Provider
    seed_dir=Path(__file__).parents[1]/'infra/db/seed'
    names=JudgeService.AGENT_BY_PHASE
    agent_seed=next(r for r in json.loads((seed_dir/'agent.json').read_text(encoding='utf-8')) if r['name']==names[phase])
    tool_seed=next(r for r in json.loads((seed_dir/'tool.json').read_text(encoding='utf-8')) if r['name']=='intellectual_property_law_search')
    _,_,_,request=setup([],phase=phase)
    provider=Provider([call(),answer('EXPLAIN_LAW')])
    async def achat(self,**kwargs):return await provider.achat(**kwargs)
    monkeypatch.setattr(LLMClient,'achat',achat)
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            llm=LLM(name='test',provider_name='test',model_name='test-model',base_url='http://localhost',api_key='test-only',context_window_tokens=32000,max_output_tokens=2048)
            tool=Tool(**{k:v for k,v in tool_seed.items() if not k.startswith('_')})
            db.add_all([llm,tool]);db.flush()
            agent=Agent(name=names[phase],system_prompt=agent_seed['system_prompt'],llm_id=llm.id,max_output_tokens=2048,is_active=True)
            db.add(agent);db.flush();db.add(AgentToolRelation(agent_id=agent.id,tool_id=tool.id));db.flush()
            async def relations(agent_id):
                rows=db.query(AgentToolRelation).filter_by(agent_id=agent_id).all()
                return [SimpleNamespace(tool_name=db.get(Tool,r.tool_id).name,config_override=r.config_override) for r in rows]
            router=SimpleNamespace(query=AsyncMock(return_value=SimpleNamespace(confidence='high',warning=None,chunks=[SimpleNamespace(text=SOURCE,final_score=.95,metadata={})])))
            router_factory=SimpleNamespace(get_router=AsyncMock(return_value=router))
            container=SimpleNamespace(cache_registry=SimpleNamespace(register=Mock()),
                agent_db=SimpleNamespace(get_agent_by_name=AsyncMock(return_value=agent),get_agent=AsyncMock(return_value=agent)),
                tool_db=SimpleNamespace(get_tools_as_map=AsyncMock(return_value={tool.name:tool})),
                agent_tool_relation_db=SimpleNamespace(get_relations_for_agent=relations),
                conversation_service=None,router_factory=router_factory)
            factory=AgentFactory(container)
            result=await JudgeService(factory).decide(request)
            assert result.decision=='EXPLAIN_LAW' and result.speech==SOURCE
            router.query.assert_awaited_once_with(query='请解释适用条件',kb_ids=tool.config['allowed_kb_ids'])
            container.tool_db.get_tools_as_map.assert_awaited_once_with([tool.name])
            router_factory.get_router.assert_awaited_once_with(tool.config['router_config_id'])
    finally:engine.dispose()

def test_runtime_has_no_virtual_court_imports():
    root=Path(__file__).parents[1]/'runtime'
    for name in ('agent/agent_runner.py','agent/react_agent.py','llm/agent_client.py','agent/execution.py','llm/exceptions.py'):
        assert 'app.services.virtual_court' not in (root/name).read_text(encoding='utf-8')
    assert not hasattr(AgentRunner,'invoke_judge')

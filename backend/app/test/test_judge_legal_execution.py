"""Actual AgentLLM/runner/service chain, with deterministic provider and tool boundaries.

These tests verify orchestration; they do not claim to evaluate real-model semantics.
"""
import asyncio
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest
from langchain_core.tools import StructuredTool
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.runtime.agent.agent_runner import AgentRunner
from app.runtime.agent.react_agent import ToolReActAgent
from app.runtime.llm.agent_client import AgentLLM
from app.utils.tokens import TokenCounter
from app.runtime.agent.tool_builder import ToolBuildError
from app.schemas.integrations.virtual_court import JudgeDecisionRequest
from app.services.virtual_court import JudgeService, JudgeContextError, JudgeTimeoutError, JudgeConfigurationError
from app.services.virtual_court.law_policy import LAW_TOOL
from app.test.judge_v2_helpers import ROOT, load

@pytest.fixture
def anyio_backend(): return 'asyncio'

SOURCE='测试条文 A（虚构测试资料）：适用条件为测试条件甲。'
MATERIAL={'confidence':'high','chunks':[{'text':SOURCE,'citation':{'title':'测试条文 A'}}]}

def answer(decision='NO_ACTION'):
    return json.dumps({'decision':decision,'target':None,
        'speech':SOURCE if decision=='EXPLAIN_LAW' else ('请人工核对适用依据。' if decision=='HANDOFF' else ''),
        'pending_points':['依据不足'] if decision=='HANDOFF' else []},ensure_ascii=False)

def call(query='请解释适用条件'):
    return {'tool_calls':[{'id':'search_1','type':'function',
        'function':{'name':LAW_TOOL,'arguments':json.dumps({'query':query},ensure_ascii=False)}}]}

class Provider:
    max_output_tokens=2048
    def __init__(self,outputs,delay=0):
        self.outputs=iter(outputs);self.messages=[];self.delay=delay
    async def achat(self,**kwargs):
        self.messages.append(copy.deepcopy(kwargs['messages']))
        await asyncio.sleep(self.delay)
        result=next(self.outputs)
        if isinstance(result,dict):
            return SimpleNamespace(content='',tool_calls=result['tool_calls'])
        return SimpleNamespace(content=result,tool_calls=None)

class Factory:
    def __init__(self,runner): self.runner=runner
    async def get_runner_by_name(self,name): return self.runner

def setup(outputs,*,phase='INVESTIGATION',material=MATERIAL,tool=True,tool_delay=0,delay=0,description='查询法律资料'):
    calls=[]
    async def search(query:str):
        calls.append(query)
        await asyncio.sleep(tool_delay)
        if isinstance(material,Exception): raise material
        return json.dumps(material,ensure_ascii=False)
    tools=[StructuredTool.from_function(coroutine=search,name=LAW_TOOL,description=description)] if tool else []
    seed=json.loads((ROOT.parents[2]/'infra/db/seed/agent.json').read_text(encoding='utf-8'))
    name='virtual_court_investigation_judge' if phase=='INVESTIGATION' else 'virtual_court_debate_judge'
    prompt=next(r['system_prompt'] for r in seed if r['name']==name)
    provider=Provider(outputs,delay)
    llm=AgentLLM(provider,'test-model',context_window_tokens=32000,max_output_tokens=2048,
        token_counter=TokenCounter(model='test-model',enable_exact_near_limit=False))
    agent=ToolReActAgent(llm,tools,prompt)
    runner=AgentRunner(1,name,agent,prompt,None,SimpleNamespace(context_window_tokens=32000,max_output_tokens=2048,model_name='test-model'))
    req=JudgeDecisionRequest.model_validate(load('cases/law-check-'+('investigation' if phase=='INVESTIGATION' else 'debate-single-party')+'.json'))
    return runner,provider,calls,req

@pytest.mark.anyio
@pytest.mark.parametrize('phase',['INVESTIGATION','DEBATE'])
async def test_real_tool_trace_and_grounded_context(phase):
    runner,provider,calls,req=setup([call(),answer('EXPLAIN_LAW')],phase=phase)
    result=await JudgeService(Factory(runner)).decide(req)
    assert result.decision=='EXPLAIN_LAW' and result.speech==SOURCE and result.state_version==req.state_version
    assert len(calls)==1 and len(provider.messages)==2
    assert any(SOURCE in m['content'] for m in provider.messages[1] if m['role']=='tool')
    assert not runner._agent.agent_llm.preserve_context  # Shared cached runner is immutable.
    assert 'state_version' not in next(m['content'] for m in provider.messages[0] if m['role']=='user')

@pytest.mark.anyio
@pytest.mark.parametrize('phase',['INVESTIGATION','DEBATE'])
@pytest.mark.parametrize('speech',['我方维持此前意见，没有法律问题需要解释。','这难道不是我方一直表达的意见吗？我方没有新的问题。'])
async def test_no_action_preserves_latest_records_without_search(phase,speech):
    runner,provider,calls,req=setup([answer()],phase=phase)
    data=req.model_dump(exclude_unset=True)
    data['records'].append({'type':'SPEECH','role':'PLAINTIFF','text':speech})
    result=await JudgeService(Factory(runner)).decide(JudgeDecisionRequest.model_validate(data))
    assert result.speech=='' and result.pending_points==[] and result.target is None
    assert not calls and speech in str(provider.messages[0])

@pytest.mark.anyio
async def test_already_answered_history_reaches_model():
    runner,provider,calls,_=setup([answer()])
    data=load('cases/law-check-completed-question-history.json')
    await JudgeService(Factory(runner)).decide(JudgeDecisionRequest.model_validate(data))
    query=next(m['content'] for m in provider.messages[0] if m['role']=='user')
    assert all(r['text'] in query for r in data['records']) and not calls

@pytest.mark.anyio
@pytest.mark.parametrize('material',[{}, {'error':'private provider diagnostic'}, {'confidence':'empty','chunks':[]},
    {'chunks':[{'text':'  '}]}, RuntimeError('private secret'), {'chunks':[]}])
async def test_failed_or_empty_retrieval_handoff_never_repairs_or_explains(material):
    runner,provider,calls,req=setup([call(),answer('EXPLAIN_LAW')],material=material)
    result=await JudgeService(Factory(runner)).decide(req)
    assert result.decision=='HANDOFF' and result.pending_points and len(provider.messages)==1 and len(calls)==1
    assert 'private' not in result.model_dump_json()

@pytest.mark.anyio
@pytest.mark.parametrize('tool',[True,False])
async def test_explanation_without_executed_search_handoff(tool):
    runner,provider,calls,req=setup([answer('EXPLAIN_LAW')],tool=tool)
    result=await JudgeService(Factory(runner)).decide(req)
    assert result.decision=='HANDOFF' and not calls and len(provider.messages)==1

@pytest.mark.anyio
async def test_missing_tool_still_allows_no_pending_question():
    runner,provider,calls,req=setup([answer()],tool=False)
    assert (await JudgeService(Factory(runner)).decide(req)).decision=='NO_ACTION'

@pytest.mark.anyio
async def test_insufficient_relevance_can_handoff_after_nonempty_search():
    runner,provider,calls,req=setup([call(),answer('HANDOFF')])
    assert (await JudgeService(Factory(runner)).decide(req)).decision=='HANDOFF'
    assert len(calls)==1

@pytest.mark.anyio
async def test_tool_build_failure_business_handoff():
    _,_,_,req=setup([])
    class Broken:
        async def get_runner_by_name(self,name): raise ToolBuildError('private diagnostic')
    result=await JudgeService(Broken()).decide(req)
    assert result.decision=='HANDOFF' and 'private' not in result.model_dump_json()

@pytest.mark.anyio
async def test_tool_result_over_budget_does_not_truncate_or_send_next_request():
    runner,provider,calls,req=setup([call()],material={'chunks':[{'text':'完整资料'*100000}]})
    with pytest.raises(JudgeContextError): await JudgeService(Factory(runner)).decide(req)
    assert len(calls)==1 and len(provider.messages)==1

@pytest.mark.anyio
async def test_tool_metadata_over_budget_fails_before_provider():
    runner,provider,calls,req=setup([],description='检索描述'*100000)
    with pytest.raises(JudgeContextError): await JudgeService(Factory(runner)).decide(req)
    assert not calls and not provider.messages

@pytest.mark.anyio
async def test_shared_retrieval_and_repair_deadline():
    runner,provider,calls,req=setup([call(),'{}',call(),answer('EXPLAIN_LAW')],tool_delay=.06)
    with pytest.raises(JudgeTimeoutError):
        await JudgeService(Factory(runner),timeout_seconds=.10).decide(req)
    assert len(calls)==2  # Second retrieval is cancelled under the original deadline.

@pytest.mark.anyio
async def test_repair_retrieves_again_and_keeps_full_request():
    runner,provider,calls,req=setup([call(),'{}',call(),answer('EXPLAIN_LAW')])
    result=await JudgeService(Factory(runner)).decide(req)
    assert result.decision=='EXPLAIN_LAW' and len(calls)==2
    assert 'schema_validation_failed' in str(provider.messages[2])

@pytest.mark.anyio
async def test_cached_runner_does_not_reuse_previous_evidence():
    runner,provider,calls,req=setup([call(),answer('EXPLAIN_LAW'),answer('EXPLAIN_LAW')])
    service=JudgeService(Factory(runner))
    assert (await service.decide(req)).decision=='EXPLAIN_LAW'
    assert (await service.decide(req)).decision=='HANDOFF'
    assert len(calls)==1

@pytest.mark.anyio
async def test_prompt_without_version_marker_is_accepted():
    runner,provider,calls,req=setup([answer()])
    assert '[JudgeAPI V2:' not in runner.system_prompt
    assert (await JudgeService(Factory(runner)).decide(req)).decision=='NO_ACTION'


def test_extension_migration_restores_only_missing_binding_and_preserves_tuning():
    from app.infra.db.database import Base,Agent,LLM,Tool,AgentToolRelation
    from app.infra.db.initializer import DatabaseManager
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    with Session(engine) as db:
        llm=LLM(name='tuned',provider_name='test',base_url='http://localhost',model_name='tuned',temperature=.23)
        law=Tool(name=LAW_TOOL,tool_schema={});other=Tool(name='unrelated',tool_schema={})
        db.add_all([llm,law,other]);db.flush()
        names=JudgeService.AGENT_BY_PHASE.values()
        agents=[Agent(name=n,system_prompt='已有人工提示词',llm_id=llm.id,max_output_tokens=3000) for n in names]
        unrelated=Agent(name='unrelated',system_prompt='keep',llm_id=llm.id)
        db.add_all(agents+[unrelated]);db.flush()
        db.add(AgentToolRelation(agent_id=agents[0].id,tool_id=other.id,config_override={'keep':True}));db.flush()
        original_ids=[a.id for a in agents]
        manager=object.__new__(DatabaseManager)
        manager._seed_agent(db,force=False);db.flush()
        for a in agents:
            assert a.system_prompt=='已有人工提示词'
            assert a.max_output_tokens==3000 and a.llm_id==llm.id
            assert db.query(AgentToolRelation).filter_by(agent_id=a.id,tool_id=law.id).count()==1
            a.system_prompt+='\n人工微调'
        manager._seed_agent(db,force=False);db.flush()
        assert [a.id for a in agents]==original_ids and all(a.system_prompt.endswith('人工微调') for a in agents)
        assert llm.temperature==.23 and unrelated.system_prompt=='keep'
        assert db.query(AgentToolRelation).count()==3
        assert db.query(AgentToolRelation).filter_by(tool_id=other.id).one().config_override=={'keep':True}
    engine.dispose()

def test_shared_fixture_integrity():
    for path,expected in load('integrity.json').items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected,path

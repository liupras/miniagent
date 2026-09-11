from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.infra.db.database import Agent,Base,LLM,Tool,AgentToolRelation
from app.infra.db.initializer import DatabaseManager
import pytest

@pytest.mark.parametrize('old_name',['virtual_court_solo_judge','virtual_court_investigation_judge'])
def test_v2_upgrade_preserves_identity_parameters_and_is_idempotent(old_name):
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            llm=LLM(name='bailian_qwen_plus',provider_name='test',base_url='http://localhost',model_name='test')
            db.add(llm); db.flush()
            old=Agent(name=old_name,system_prompt='旧提示词',llm_id=llm.id,max_output_tokens=3072)
            db.add(old); db.flush()
            original=old.id
            tool=Tool(name='intellectual_property_law_search',tool_schema={})
            db.add(tool); db.flush()
            db.add(AgentToolRelation(agent_id=old.id,tool_id=tool.id)); db.flush()
            manager=object.__new__(DatabaseManager)
            manager._seed_agent(db,force=False); db.flush()
            current=db.query(Agent).filter_by(name='virtual_court_investigation_judge').one()
            assert current.id==original and current.max_output_tokens==3072 and current.llm_id==llm.id
            assert current.system_prompt == '旧提示词'
            assert db.query(AgentToolRelation).filter_by(agent_id=original).count()==1
            current.system_prompt+='\n人工微调'
            manager._seed_agent(db,force=False); db.flush()
            assert current.system_prompt.endswith('人工微调')
            assert db.query(Agent).filter_by(name='virtual_court_debate_judge').count()==1
    finally: engine.dispose()


def test_migration_preserves_custom_model_when_seed_default_is_missing():
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            llm=LLM(name='custom-model',provider_name='test',base_url='http://localhost',model_name='test')
            db.add(llm); db.flush()
            old=Agent(name='virtual_court_investigation_judge',system_prompt='旧提示词',llm_id=llm.id,max_output_tokens=3000)
            db.add(old); db.flush()
            object.__new__(DatabaseManager)._seed_agent(db,force=False)
            assert old.system_prompt == '旧提示词'
            assert old.llm_id==llm.id and old.max_output_tokens==3000
    finally: engine.dispose()

def test_explicit_prompt_refresh_preserves_model_parameters():
    import json
    from app.infra.db.initializer import SEED_DIR
    row=next(r for r in json.loads((SEED_DIR/'agent.json').read_text(encoding='utf-8')) if r['name']=='virtual_court_investigation_judge')
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            llm=LLM(name='custom',provider_name='test',base_url='http://localhost',model_name='test')
            db.add(llm);db.flush()
            agent=Agent(name=row['name'],system_prompt='人工调整',llm_id=llm.id,max_output_tokens=3000)
            db.add(agent);db.flush();original=agent.id
            manager=object.__new__(DatabaseManager)
            manager._seed_agent_row(db,row,refresh_prompt=True)
            assert agent.system_prompt==row['system_prompt'] and '[JudgeAPI V2:' not in agent.system_prompt
            assert agent.id==original and agent.llm_id==llm.id and agent.max_output_tokens==3000
            agent.system_prompt+='\n人工修改'
            manager._seed_agent_row(db,row)
            assert agent.system_prompt.endswith('人工修改')
    finally:engine.dispose()

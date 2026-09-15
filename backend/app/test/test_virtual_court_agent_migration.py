import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.infra.db.database import Agent, AgentToolRelation, Base, LLM, Tool
from scripts.upgrade_judge_v2 import (
    FLOW_AGENT,
    JUDGE_AGENTS,
    LAW_CHECK_AGENT,
    LAW_TOOL,
    RETIRED_AGENT,
    migrate_judge_agents,
)


def make_database(*, missing_agent=None, include_tool=True, include_law_agent=False):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        llm = LLM(
            name="custom-judge-model",
            provider_name="test",
            base_url="http://localhost",
            model_name="judge-test",
            temperature=0.23,
        )
        db.add(llm)
        db.flush()
        for name in (FLOW_AGENT, RETIRED_AGENT):
            if name == missing_agent:
                continue
            db.add(Agent(
                name=name,
                description="旧描述",
                system_prompt="旧提示词",
                llm_id=llm.id,
                max_output_tokens=3000,
                is_active=True,
            ))
        if include_law_agent:
            db.add(Agent(
                name=LAW_CHECK_AGENT,
                description="旧法律描述",
                system_prompt="旧法律提示词",
                llm_id=llm.id,
                max_output_tokens=4095,
                is_active=False,
            ))
        db.add(Agent(
            name="unrelated",
            description="keep-description",
            system_prompt="keep-prompt",
            llm_id=llm.id,
            max_output_tokens=1777,
            is_active=True,
        ))
        if include_tool:
            law_tool = Tool(name=LAW_TOOL, tool_schema={})
            db.add(law_tool)
            db.flush()
            for agent in db.query(Agent).filter(
                Agent.name.in_((FLOW_AGENT, RETIRED_AGENT))
            ).all():
                db.add(AgentToolRelation(agent_id=agent.id, tool_id=law_tool.id))
        db.commit()
    return engine


def snapshot(db):
    agents = db.execute(select(Agent).order_by(Agent.id)).scalars().all()
    relations = db.execute(
        select(AgentToolRelation).order_by(
            AgentToolRelation.agent_id,
            AgentToolRelation.tool_id,
        )
    ).scalars().all()
    return (
        [
            (
                agent.id,
                agent.name,
                agent.description,
                agent.system_prompt,
                agent.llm_id,
                agent.max_output_tokens,
                agent.is_active,
            )
            for agent in agents
        ],
        [(relation.agent_id, relation.tool_id) for relation in relations],
    )


def test_migration_creates_law_agent_moves_binding_and_preserves_tuning():
    engine = make_database()
    try:
        with Session(engine) as db, db.begin():
            flow = db.query(Agent).filter_by(name=FLOW_AGENT).one()
            flow_before = (flow.id, flow.llm_id, flow.max_output_tokens, flow.is_active)
            llm_before = db.query(LLM).one()
            llm_values = (
                llm_before.id,
                llm_before.temperature,
                llm_before.max_output_tokens,
            )
            assert migrate_judge_agents(db) is True

        with Session(engine) as db:
            agents = {agent.name: agent for agent in db.query(Agent).all()}
            assert set(JUDGE_AGENTS) <= set(agents)
            assert RETIRED_AGENT not in agents
            flow = agents[FLOW_AGENT]
            assert (
                flow.id,
                flow.llm_id,
                flow.max_output_tokens,
                flow.is_active,
            ) == flow_before

            law_agent = agents[LAW_CHECK_AGENT]
            assert (
                law_agent.llm_id,
                law_agent.max_output_tokens,
                law_agent.is_active,
            ) == (flow.llm_id, flow.max_output_tokens, flow.is_active)

            tool = db.query(Tool).filter_by(name=LAW_TOOL).one()
            counts = {
                name: db.query(AgentToolRelation).filter_by(
                    agent_id=agents[name].id,
                    tool_id=tool.id,
                ).count()
                for name in JUDGE_AGENTS
            }
            assert counts == {
                LAW_CHECK_AGENT: 1,
                FLOW_AGENT: 0,
            }
            unrelated = agents["unrelated"]
            assert (
                unrelated.description,
                unrelated.system_prompt,
                unrelated.max_output_tokens,
            ) == ("keep-description", "keep-prompt", 1777)
            llm = db.query(LLM).one()
            assert (llm.id, llm.temperature, llm.max_output_tokens) == llm_values
    finally:
        engine.dispose()


def test_second_migration_makes_no_database_changes():
    engine = make_database()
    try:
        with Session(engine) as db, db.begin():
            assert migrate_judge_agents(db) is True
        with Session(engine) as db:
            first = snapshot(db)
        with Session(engine) as db, db.begin():
            assert migrate_judge_agents(db) is False
        with Session(engine) as db:
            assert snapshot(db) == first
    finally:
        engine.dispose()


def test_existing_law_agent_keeps_its_runtime_tuning():
    engine = make_database(include_law_agent=True)
    try:
        with Session(engine) as db:
            law = db.query(Agent).filter_by(name=LAW_CHECK_AGENT).one()
            before = (law.id, law.llm_id, law.max_output_tokens, law.is_active)
        with Session(engine) as db, db.begin():
            migrate_judge_agents(db)
        with Session(engine) as db:
            law = db.query(Agent).filter_by(name=LAW_CHECK_AGENT).one()
            assert (law.id, law.llm_id, law.max_output_tokens, law.is_active) == before
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "missing_agent, include_tool",
    [(FLOW_AGENT, True), (None, False)],
)
def test_missing_prerequisite_rolls_back_everything(missing_agent, include_tool):
    engine = make_database(missing_agent=missing_agent, include_tool=include_tool)
    try:
        with Session(engine) as db:
            before = snapshot(db)
        with pytest.raises(RuntimeError):
            with Session(engine) as db, db.begin():
                migrate_judge_agents(db)
        with Session(engine) as db:
            assert snapshot(db) == before
            assert db.query(Agent).filter_by(name=LAW_CHECK_AGENT).count() == 0
    finally:
        engine.dispose()

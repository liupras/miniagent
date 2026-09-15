import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infra.db.database import Agent, AgentToolRelation, Base, LLM, Tool
from app.infra.db.initializer import DatabaseManager


ROOT = Path(__file__).parents[1] / "infra" / "db" / "seed"


def seed_rows(filename):
    return json.loads((ROOT / filename).read_text(encoding="utf-8"))


def test_law_check_agent_has_isolated_prompt_and_tool():
    rows = seed_rows("agent.json")
    row = next(row for row in rows if row["name"] == "virtual_court_law_check_judge")
    prompt = row["system_prompt"]

    assert row["is_active"] and row["max_output_tokens"] == 2048
    for rule in (
        "latest_speech",
        "reference_context",
        "NO_ACTION",
        "EXPLAIN_LAW",
        "HANDOFF",
        "intellectual_property_law_search",
        "不能单独触发解释",
        "检索失败",
        "依据不足",
    ):
        assert rule in prompt

    tools = seed_rows("agent_tool_relation.json")
    assert [
        relation["_tool_name"]
        for relation in tools
        if relation["_agent_name"] == row["name"]
    ] == ["intellectual_property_law_search"]


def test_investigation_agent_prompt_contains_only_investigation_rules():
    name = "virtual_court_investigation_judge"
    row = next(row for row in seed_rows("agent.json") if row["name"] == name)
    prompt = row["system_prompt"]

    assert row["is_active"] and row["max_output_tokens"] == 2048
    assert "不得判断证据真伪" in prompt
    for rule in (
        "ASK",
        "COMPLETE",
        "HANDOFF",
        "allowed_actions",
        "allowed_targets",
    ):
        assert rule in prompt
    for rule in (
        "DEBATE",
        "INVESTIGATION",
        "CONTINUE",
        "current_issue",
        "investigation_summary",
        "NO_ACTION",
        "EXPLAIN_LAW",
        "intellectual_property_law_search",
    ):
        assert rule not in prompt

    tools = seed_rows("agent_tool_relation.json")
    assert not [relation for relation in tools if relation["_agent_name"] == name]


def test_two_judge_agents_load_and_only_law_check_has_law_tool():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add(LLM(
                name="bailian_qwen_plus",
                provider_name="test",
                base_url="http://localhost",
                model_name="bailian-test",
            ))
            db.add(LLM(
                name="ollama_qwen_4b",
                provider_name="test",
                base_url="http://localhost",
                model_name="ollama-test",
            ))
            for tool_name in (
                "china_legal_kb_router",
                "web_search",
                "sql_agent",
                "intellectual_property_law_search",
            ):
                db.add(Tool(name=tool_name, tool_schema={}))
            db.flush()

            manager = object.__new__(DatabaseManager)
            manager._seed_agent(db, force=False)
            manager._seed_agent_tool_relation(db, force=False)
            db.flush()

            names = {
                "virtual_court_law_check_judge",
                "virtual_court_investigation_judge",
            }
            agents = db.query(Agent).filter(Agent.name.in_(names)).all()
            assert {agent.name for agent in agents} == names

            bindings = {
                agent.name: db.query(AgentToolRelation)
                .filter_by(agent_id=agent.id)
                .count()
                for agent in agents
            }
            assert bindings == {
                "virtual_court_law_check_judge": 1,
                "virtual_court_investigation_judge": 0,
            }
    finally:
        engine.dispose()

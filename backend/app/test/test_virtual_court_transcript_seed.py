"""Seed contract for the dedicated VirtualCourt transcript writer."""

import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infra.db.database import Agent, AgentToolRelation, Base, LLM, Tool
from app.infra.db.initializer import DatabaseManager


ROOT = Path(__file__).parents[1] / "infra" / "db" / "seed"
AGENT_NAME = "virtual_court_transcript_writer"


def seed_rows(filename):
    return json.loads((ROOT / filename).read_text(encoding="utf-8"))


def test_transcript_agent_prompt_and_runtime_limits_are_frozen():
    rows = seed_rows("agent.json")
    matches = [row for row in rows if row["name"] == AGENT_NAME]
    assert len(matches) == 1

    row = matches[0]
    prompt = row["system_prompt"]
    assert row["is_active"] is True
    assert row["_llm_name"] == "bailian_qwen_plus"
    assert row["max_output_tokens"] == 16384

    for rule in (
        "case_context",
        "records",
        "SPEECH",
        "SUMMARY",
        "必须保持该顺序",
        "不得伪造成某个角色的逐字发言",
        "不得补充输入中不存在",
        "不得把当事人主张改写为已经查明的事实",
        "只包含 transcript 字段",
        "不得输出 Markdown",
        "state_version",
        "最多 64000 个 Unicode 码点",
    ):
        assert rule in prompt


def test_transcript_agent_has_no_static_tool_binding():
    relations = seed_rows("agent_tool_relation.json")
    assert not [
        relation
        for relation in relations
        if relation["_agent_name"] == AGENT_NAME
    ]


def test_existing_database_is_supplemented_idempotently_without_tools():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            llms = {
                "bailian_qwen_plus": LLM(
                    name="bailian_qwen_plus",
                    provider_name="test",
                    base_url="http://localhost",
                    model_name="bailian-test",
                ),
                "ollama_qwen_4b": LLM(
                    name="ollama_qwen_4b",
                    provider_name="test",
                    base_url="http://localhost",
                    model_name="ollama-test",
                ),
            }
            db.add_all(llms.values())
            for tool_name in (
                "china_legal_kb_router",
                "web_search",
                "sql_agent",
                "intellectual_property_law_search",
            ):
                db.add(Tool(name=tool_name, tool_schema={}))
            db.flush()

            # Simulate an existing installation that predates TranscriptAPI.
            db.add_all(
                [
                    Agent(
                        name="virtual_court_law_check_judge",
                        description="existing",
                        system_prompt="existing",
                        llm_id=llms["bailian_qwen_plus"].id,
                        is_active=True,
                    ),
                    Agent(
                        name="virtual_court_investigation_judge",
                        description="existing",
                        system_prompt="existing",
                        llm_id=llms["bailian_qwen_plus"].id,
                        is_active=True,
                    ),
                ]
            )
            db.flush()

            manager = object.__new__(DatabaseManager)
            manager._seed_agent(db, force=False)
            manager._seed_agent_tool_relation(db, force=False)
            db.flush()

            agent = db.query(Agent).filter_by(name=AGENT_NAME).one()
            assert agent.is_active is True
            assert agent.max_output_tokens == 16384
            assert agent.llm_id == llms["bailian_qwen_plus"].id
            assert (
                db.query(AgentToolRelation).filter_by(agent_id=agent.id).count()
                == 0
            )

            manager._seed_agent(db, force=False)
            manager._seed_agent_tool_relation(db, force=False)
            db.flush()

            assert db.query(Agent).filter_by(name=AGENT_NAME).count() == 1
            assert (
                db.query(AgentToolRelation).filter_by(agent_id=agent.id).count()
                == 0
            )
    finally:
        engine.dispose()

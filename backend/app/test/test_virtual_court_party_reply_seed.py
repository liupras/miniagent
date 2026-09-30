import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infra.db.database import Agent, AgentToolRelation, Base, LLM
from app.infra.db.initializer import DatabaseManager


ROOT = Path(__file__).parents[1] / "infra" / "db" / "seed"
AGENT_NAME = "virtual_court_party_responder"


def seed_rows(filename):
    return json.loads((ROOT / filename).read_text(encoding="utf-8"))


def test_party_responder_prompt_and_runtime_limits_are_frozen():
    matches = [row for row in seed_rows("agent.json") if row["name"] == AGENT_NAME]
    assert len(matches) == 1
    row = matches[0]
    assert row["is_active"] is True
    assert row["_llm_name"] == "bailian_qwen_plus"
    assert row["max_output_tokens"] == 2048
    for rule in (
        "role 指定你代表原告还是被告",
        "正面回答法官提出的具体问题",
        "符合 role 所代表一方的诉讼立场",
        "同一方已经作出的陈述保持一致",
        "不得随机选择肯定或否定答案",
        "不得编造",
        "现有记录中没有该信息",
        "只包含 speech 字段",
        "不得输出 Markdown",
        "state_version",
        "最多 1000 个 Unicode 码点",
    ):
        assert rule in row["system_prompt"]


def test_party_responder_has_no_static_tool_binding():
    relations = seed_rows("agent_tool_relation.json")
    assert not [r for r in relations if r["_agent_name"] == AGENT_NAME]


def test_existing_database_is_supplemented_and_prompt_is_refreshed():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            llm = LLM(
                name="bailian_qwen_plus",
                provider_name="test",
                base_url="http://localhost",
                model_name="bailian-test",
            )
            db.add(llm)
            db.flush()
            manager = object.__new__(DatabaseManager)

            manager._seed_agent(db, force=False)
            db.flush()
            agent = db.query(Agent).filter_by(name=AGENT_NAME).one()
            assert agent.llm_id == llm.id
            assert db.query(AgentToolRelation).filter_by(agent_id=agent.id).count() == 0

            agent.system_prompt = "legacy party reply prompt"
            manager._seed_agent(db, force=False)
            db.flush()
            assert db.query(Agent).filter_by(name=AGENT_NAME).count() == 1
            assert "只包含 speech 字段" in agent.system_prompt
            assert "legacy party reply prompt" not in agent.system_prompt
    finally:
        engine.dispose()

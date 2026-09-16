"""Migrate the active Judge V2 agents and law-tool binding transactionally.

The migration updates the two active Judge prompts, creates the law-check Agent
when absent, and moves the law-search binding to it. Active Agent runtime tuning
and all unrelated rows are preserved.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session

from app.infra.db.database import (
    Agent,
    AgentToolRelation,
    Tool,
)
from app.infra.db.initializer import DatabaseManager, SEED_DIR


LAW_CHECK_AGENT = "virtual_court_law_check_judge"
FLOW_AGENT = "virtual_court_investigation_judge"
JUDGE_AGENTS = (LAW_CHECK_AGENT, FLOW_AGENT)
LAW_TOOL = "intellectual_property_law_search"


def _judge_seed_rows() -> dict[str, dict]:
    rows = json.loads((SEED_DIR / "agent.json").read_text(encoding="utf-8"))
    by_name = {row["name"]: row for row in rows if row.get("name") in JUDGE_AGENTS}
    missing = set(JUDGE_AGENTS) - set(by_name)
    if missing:
        raise RuntimeError(f"Judge seed rows missing: {sorted(missing)}")
    return by_name


def migrate_judge_agents(db: Session) -> bool:
    """Apply the migration inside the caller's transaction.

    Returns ``True`` if the database changed. Any unmet prerequisite raises,
    allowing the surrounding transaction to roll back completely.
    """

    seeds = _judge_seed_rows()
    flow_agent = db.query(Agent).filter_by(name=FLOW_AGENT).one_or_none()
    if flow_agent is None:
        raise RuntimeError(f"Required Judge agent missing: {FLOW_AGENT}")

    law_tool = db.query(Tool).filter_by(name=LAW_TOOL).one_or_none()
    if law_tool is None:
        raise RuntimeError(f"Required tool missing: {LAW_TOOL}")

    changed = False
    law_agent = db.query(Agent).filter_by(name=LAW_CHECK_AGENT).one_or_none()
    if law_agent is None:
        law_seed = seeds[LAW_CHECK_AGENT]
        law_agent = Agent(
            name=LAW_CHECK_AGENT,
            description=law_seed["description"],
            system_prompt=law_seed["system_prompt"],
            llm_id=flow_agent.llm_id,
            max_output_tokens=flow_agent.max_output_tokens,
            is_active=flow_agent.is_active,
        )
        db.add(law_agent)
        db.flush()
        changed = True

    agents = {FLOW_AGENT: flow_agent, LAW_CHECK_AGENT: law_agent}
    for name, agent in agents.items():
        seed = seeds[name]
        for field in ("description", "system_prompt"):
            value = seed[field]
            if getattr(agent, field) != value:
                setattr(agent, field, value)
                changed = True

    removed = (
        db.query(AgentToolRelation)
        .filter(
            AgentToolRelation.agent_id.in_(
                [flow_agent.id]
            ),
            AgentToolRelation.tool_id == law_tool.id,
        )
        .delete(synchronize_session=False)
    )
    changed = changed or bool(removed)

    law_binding = db.query(AgentToolRelation).filter_by(
        agent_id=law_agent.id,
        tool_id=law_tool.id,
    ).one_or_none()
    if law_binding is None:
        db.add(AgentToolRelation(agent_id=law_agent.id, tool_id=law_tool.id))
        changed = True

    db.flush()
    loaded = db.query(Agent).filter(Agent.name.in_(JUDGE_AGENTS)).all()
    if len(loaded) != len(JUDGE_AGENTS):
        raise RuntimeError("Judge migration incomplete")
    if any(agent.system_prompt != seeds[agent.name]["system_prompt"] for agent in loaded):
        raise RuntimeError("Judge prompt verification failed")

    binding_counts = {
        agent.name: db.query(AgentToolRelation).filter_by(
            agent_id=agent.id,
            tool_id=law_tool.id,
        ).count()
        for agent in loaded
    }
    expected = {LAW_CHECK_AGENT: 1, FLOW_AGENT: 0}
    if binding_counts != expected:
        raise RuntimeError(
            f"Judge law-tool binding verification failed: {binding_counts}"
        )
    return changed


def main() -> None:
    manager = DatabaseManager()
    try:
        with manager.SessionLocal.begin() as db:
            changed = migrate_judge_agents(db)
        status = "updated" if changed else "already current"
        print(f"Split Judge V2 migration complete ({status}).")
        print("Restart the service to discard cached Agent runners.")
    finally:
        manager.engine.dispose()


if __name__ == "__main__":
    main()

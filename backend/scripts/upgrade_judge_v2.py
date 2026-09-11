"""Upgrade just the two Judge Agents transactionally. Restart service after running.

No schema rebuild, no force reseed, no unrelated Agent/LLM changes.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.infra.db.initializer import DatabaseManager, SEED_DIR
from app.infra.db.database import Agent, Tool, AgentToolRelation

def main():
    manager = DatabaseManager()
    names = {'virtual_court_investigation_judge', 'virtual_court_debate_judge'}
    rows = json.loads((SEED_DIR / 'agent.json').read_text(encoding='utf-8'))
    try:
        with manager.SessionLocal.begin() as db:
            for row in rows:
                if row['name'] in names:
                    manager._seed_agent_row(db, row, refresh_prompt=True)
            db.flush()
            agents = db.query(Agent).filter(Agent.name.in_(names)).all()
            prompts = {row['name']:row['system_prompt'] for row in rows if row['name'] in names}
            if len(agents) != 2 or any(a.system_prompt != prompts[a.name] for a in agents):
                raise RuntimeError('Judge upgrade incomplete; transaction rolled back')
            tool = db.query(Tool).filter_by(name='intellectual_property_law_search').one()
            for agent in agents:
                if db.query(AgentToolRelation).filter_by(agent_id=agent.id, tool_id=tool.id).count() != 1:
                    raise RuntimeError('Judge tool binding incomplete; transaction rolled back')
        print('Both Judge Agents and law-search bindings upgraded. Restart service to discard cached runners.')
    finally:
        manager.engine.dispose()

if __name__ == '__main__':
    main()

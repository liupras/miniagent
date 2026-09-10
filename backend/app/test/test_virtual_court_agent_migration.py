from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infra.db.database import Agent, Base, LLM
from app.infra.db.initializer import DatabaseManager


def test_seed_renames_judge_without_overwriting_tuned_configuration():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            llm = LLM(
                name="bailian_qwen_plus", provider_name="test",
                base_url="http://localhost", model_name="test",
            )
            db.add(llm)
            db.flush()
            legacy = Agent(
                name="virtual_court_solo_judge", system_prompt="已调试的提示词",
                llm_id=llm.id, max_output_tokens=3072,
            )
            db.add(legacy)
            db.flush()
            original_id = legacy.id

            # The seeder only uses the supplied session; no application DB is opened.
            manager = object.__new__(DatabaseManager)
            for _ in range(2):
                manager._seed_agent(db, force=False)
                db.flush()

            investigation = db.query(Agent).filter_by(
                name="virtual_court_investigation_judge"
            ).one()
            assert investigation.id == original_id
            assert investigation.system_prompt == "已调试的提示词"
            assert investigation.max_output_tokens == 3072
            assert investigation.llm_id == llm.id
            assert db.query(Agent).filter_by(name="virtual_court_solo_judge").count() == 0
            assert db.query(Agent).filter_by(name="virtual_court_debate_judge").count() == 1
    finally:
        engine.dispose()

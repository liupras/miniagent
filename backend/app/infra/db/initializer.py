#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-10
# @description: Database initialization and migration management

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings
from app.infra.db.database import (
    Base, Permission, Role, RolePermissionRelation, User, LLM, Embedding, Agent, KnowledgeBase, Tool,Domain,
    UserAgentRelation, AgentToolRelation, StrategyConfig, I18n, SystemSetting,
    RouterConfig, UserRoleRelation
)
from app.core.security import bcrypt_hash

# Directory that contains all seed JSON files.
SEED_DIR = Path(__file__).parent / "seed"


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _load(filename: str) -> List[Dict[str, Any]]:
    """
    Load and return the contents of a seed JSON file.

    The file must contain a JSON array.  If the file is missing or malformed,
    an empty list is returned and a warning is logged so that a missing seed
    file never crashes the startup sequence.
    """
    path = SEED_DIR / filename
    if not path.exists():
        logger.warning(f"[SeedLoader] Seed file not found, skipping: {path}")
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            logger.error(
                f"[SeedLoader] Expected a JSON array in {path}, "
                f"got {type(data).__name__}"
            )
            return []
        logger.debug(f"[SeedLoader] Loaded {len(data)} record(s) from {filename}")
        return data
    except json.JSONDecodeError as exc:
        logger.error(f"[SeedLoader] JSON parse error in {path}: {exc}")
        return []


def _strip_meta(record: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *record* with all keys that start with '_' removed."""
    return {k: v for k, v in record.items() if not k.startswith("_")}

class DatabaseManager:
    """Database Manager Class"""

    def __init__(self, database_url: Optional[str] = None):
        if database_url is None:
            db_path = settings.get_sqlite_path()
            database_url = f"sqlite:///{db_path}"

        self.database_url = database_url
        self.engine = create_engine(
            database_url,
            echo=settings.debug,
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )

    # ── Schema ────────────────────────────────────────────────────────────

    def init_database(self, force: bool = False) -> bool:
        """Create all tables, optionally dropping them first."""
        try:
            if force:
                logger.warning("🗑️ Forced rebuild mode: Deleting all tables...")
                Base.metadata.drop_all(bind=self.engine)
                logger.success("✅ All tables have been deleted.")

            logger.info("🔨 Creating database tables...")
            Base.metadata.create_all(bind=self.engine)
            logger.success("✅ Database tables created successfully!")

            self._configure_sqlite()
            self._show_tables()
            return True

        except Exception as exc:
            logger.error(f"❌ Database initialization failed: {exc}")
            return False

    def _configure_sqlite(self):
        """Apply SQLite performance pragmas."""
        try:
            logger.info("⚙️ Configure SQLite parameters...")
            with self.engine.connect() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                result = conn.execute(text("PRAGMA journal_mode")).fetchone()
                logger.info(f"   Journal Mode: {result[0]}")
                conn.execute(text("PRAGMA synchronous=NORMAL"))
                conn.execute(text("PRAGMA cache_size=10000"))
                conn.execute(text("PRAGMA temp_store=MEMORY"))
                conn.execute(text("PRAGMA foreign_keys=ON"))
                conn.commit()
            logger.success("✅ SQLite configuration complete!")
        except Exception as exc:
            logger.warning(f"⚠️ SQLite configuration failed: {exc}")

    def _show_tables(self):
        """Log the names of all tables currently in the database."""
        tables = inspect(self.engine).get_table_names()
        logger.info(f"📋 Tables in the database ({len(tables)}):")
        for t in tables:
            logger.info(f"   - {t}")

    def check_database(self) -> bool:
        """Return True when the database exists and contains at least one table."""
        try:
            tables = inspect(self.engine).get_table_names()
            if not tables:
                logger.warning("⚠️ There is no table in the database.")
                return False
            logger.info(f"✅ The database is normal and contains {len(tables)} tables.")
            return True
        except Exception as exc:
            logger.error(f"❌ Database check failed: {exc}")
            return False

    def upgrade_schema(self) -> bool:
        """Create any tables that are defined in the ORM but missing from the DB."""
        try:
            logger.info("🔄 Check database schema updates...")
            existing = set(inspect(self.engine).get_table_names())
            required = set(Base.metadata.tables.keys())
            missing  = required - existing

            if missing:
                logger.warning(f"⚠️ Missing tables: {missing}")
                logger.info("🔨 Creating missing tables...")
                Base.metadata.create_all(bind=self.engine)
                logger.success("✅ Missing tables have been created.")
            else:
                logger.success("✅ The database schema is up-to-date.")
            return True
        except Exception as exc:
            logger.error(f"❌ Schema upgrade failed: {exc}")
            return False

    # ── Seed orchestration ────────────────────────────────────────────────

    def seed_data(self, force: bool = False) -> bool:
        """
        Populate all tables from seed JSON files in seed/.
        """
        db = self.SessionLocal()
        try:
            logger.info("🌱 Start filling in preset data...")

            steps = [
                (self._seed_llm,              "LLM"),
                (self._seed_embedding,        "Embedding"),
                (self._seed_users,            "User"),
                (self._seed_router_config,   "RouterConfig"),
                (self._seed_tools,            "Tool"),
                (self._seed_domains,          "Domain"),
                (self._seed_knowledge_base,  "KnowledgeBase"),
                (self._seed_system_setting,  "SystemSetting"),
                (self._seed_i18n,             "I18n"),
                (self._seed_strategy_config, "StrategyConfig"),
                (self._seed_agent,           "Agent"),
                (self._seed_role,              "Role"),
                (self._seed_permission,        "Permission"),               
                (self._seed_user_agent_relation,        "UserAgentRelation"),
                (self._seed_agent_tool_relation,        "AgentToolRelation"),
                (self._seed_role_permission_relation, "RolePermissionRelation"),
                (self._seed_user_role_relation, "UserRoleRelation"),
            ]

            for fn, label in steps:
                fn(db, force)
                db.flush()
                db.commit()
                logger.debug(f"   ✔ {label} committed")

            logger.success("✅ Preset data filling complete!")
            return True

        except Exception as exc:
            db.rollback()
            logger.error(f"❌ Failed to fill preset data: {exc}")
            return False
        finally:
            db.close()

    # ── Individual seed methods ───────────────────────────────────────────

    def _seed_llm(self, db: Session, force: bool):
        logger.info("📝 Seeding LLM configurations...")
        for raw in _load("llm.json"):
            row = _strip_meta(raw)
            existing = db.query(LLM).filter_by(
                provider_name=row["provider_name"],
                model_name=row["model_name"],
            ).first()
            if existing:
                if force:
                    for k, v in row.items():
                        if k != "provider_name":
                            setattr(existing, k, v)
                    logger.info(f"   ✓ Update LLM: {row['provider_name']}/{row['model_name']}")
                else:
                    logger.info(f"   - Skip LLM: {row['provider_name']}/{row['model_name']}")
            else:
                db.add(LLM(**row))
                logger.info(f"   + Create LLM: {row['provider_name']}/{row['model_name']}")

    def _seed_embedding(self, db: Session, force: bool):
        logger.info("📝 Seeding Embedding configurations...")
        for raw in _load("embedding.json"):
            row = _strip_meta(raw)
            existing = db.query(Embedding).filter_by(name=row["name"]).first()
            if existing:
                if force:
                    for k, v in row.items():
                        if k != "name":
                            setattr(existing, k, v)
                    logger.info(f"   ✓ Update Embedding: {row['name']}")
                else:
                    logger.info(f"   - Skip Embedding: {row['name']}")
            else:
                db.add(Embedding(**row))
                logger.info(f"   + Create Embedding: {row['name']}")                

    def _seed_users(self, db: Session, force: bool):
        """
        Load users from user.json.
        """
        logger.info("📝 Seeding users...")
        for row in _load("user.json"):
            plain_password = row.pop("password", None)
            if not plain_password:
                logger.warning(
                    f"   ⚠️ User '{row.get('username')}' has no 'password' field, skipping"
                )
                continue
            existing = db.query(User).filter_by(username=row["username"]).first()
            if existing:
                logger.info(f"   - Skip existing user: {row['username']}")
            else:
                row["password_hash"] = bcrypt_hash(plain_password)
                db.add(User(**row))
                logger.info(f"   + Create user: {row['username']}")

    def _seed_router_config(self, db: Session, force: bool):
        logger.info("📝 Seeding router_configs...")
        for raw in _load("router_config.json"):
            row = _strip_meta(raw)
            existing = db.query(RouterConfig).filter_by(config_id=row["config_id"]).first()
            if existing:
                if force:
                    for k, v in row.items():
                        if k != "config_id":
                            setattr(existing, k, v)
                    logger.info(f"   ✓ Update RouterConfig: {row['config_id']}")
                else:
                    logger.info(f"   - Skip RouterConfig: {row['config_id']}")
            else:
                db.add(RouterConfig(**row))
                logger.info(f"   + Create RouterConfig: {row['config_id']}")

    def _seed_tools(self, db: Session, force: bool):
        logger.info("📝 Seeding tools...")
        for raw in _load("tool.json"):
            row = _strip_meta(raw)
            existing = db.query(Tool).filter_by(name=row["name"]).first()
            if existing:
                if force:
                    for k, v in row.items():
                        if k != "name":
                            setattr(existing, k, v)
                    logger.info(f"   ✓ Update Tool: {row['name']}")
                else:
                    logger.info(f"   - Skip Tool: {row['name']}")
            else:
                db.add(Tool(**row))
                logger.info(f"   + Create Tool: {row['name']}")

    def _seed_domains(self, db: Session, force: bool):
        """
        Seed Domain rows from seed/domain.json.

        Domain.name is the natural key (unique, used as the DomainPlugin
        routing key).  On force=True every mutable field is updated except
        name itself.

        These rows must exist before KnowledgeBase rows are created because
        KnowledgeBase.domain_id is a non-nullable FK to domain.id.
        """
        logger.info("📝 Seeding domains...")
        for raw in _load("domain.json"):
            row = _strip_meta(raw)          # strips _comment and any other _ keys
            existing = db.query(Domain).filter_by(name=row["name"]).first()
            if existing:
                if force:
                    for k, v in row.items():
                        if k != "name":
                            setattr(existing, k, v)
                    logger.info(f"   ✓ Update Domain: {row['name']}")
                else:
                    logger.info(f"   - Skip Domain: {row['name']}")
            else:
                db.add(Domain(**row))
                logger.info(f"   + Create Domain: {row['name']}")

    def _seed_knowledge_base(self, db: Session, force: bool):
        """
        Seed KnowledgeBase rows.
        Resolves "_llm_provider_name" + "_llm_model_name" → llm.id.
        """
        logger.info("📝 Seeding knowledge bases...")
        for raw in _load("knowledge_base.json"):
            row = _strip_meta(raw)

            # ── Resolve llm_provider ─────────────────────────────────────
            llm_name = raw.get("_llm_name")
            embedding_name = raw.get("_embedding_name")
            if llm_name:
                llm = db.query(LLM).filter_by(
                    name=llm_name
                ).first()
                if llm:
                    row["llm_id"] = llm.id
                else:
                    logger.warning(
                        f"   ⚠️ LLM '{llm_name}' not found "
                        f"for KB '{row['name']}', llm_provider will be NULL"
                    )
            if embedding_name:
                embedding_name = raw.get("_embedding_name") 
                embedding = db.query(Embedding).filter_by(
                    name=embedding_name
                ).first()
                if embedding:
                    row["embedding_id"] = embedding.id
                else:
                    logger.warning(
                        f"   ⚠️ Embedding '{embedding_name}' not found "
                        f"for KB '{row['name']}', embedding_id will be NULL"
                    )

            domain_name = raw.get("_domain_name")
            if not domain_name:
                logger.warning(
                    f"   ⚠️ KnowledgeBase '{row['name']}' missing '_domain_name', "
                    f"defaulting to 'general'"
                )
                domain_name = "general"
            domain = db.query(Domain).filter_by(name=domain_name).first()
            if domain:
                row["domain_id"] = domain.id
            else:
                logger.warning(
                    f"   ⚠️ Domain '{domain_name}' not found for KB '{row['name']}', "
                    f"skipping"
                )
                continue

            existing = db.query(KnowledgeBase).filter_by(name=row["name"]).first()
            if existing:
                if force:
                    for k, v in row.items():
                        if k != "name":
                            setattr(existing, k, v)
                    logger.info(f"   ✓ Update KnowledgeBase: {row['name']}")
                else:
                    logger.info(f"   - Skip KnowledgeBase: {row['name']}")
            else:
                db.add(KnowledgeBase(**row))
                logger.info(f"   + Create KnowledgeBase: {row['name']}")

    def _seed_system_setting(self, db: Session, force: bool):
        """
        Seed SystemSetting rows.
        Read-only rows (is_readonly=true) are never overwritten even when force=True.
        """
        logger.info("📝 Seeding system settings...")
        for row in _load("system_setting.json"):
            existing = db.query(SystemSetting).filter_by(key=row["key"]).first()
            if existing:
                if force and not existing.is_readonly:
                    for k, v in row.items():
                        if k != "key":
                            setattr(existing, k, v)
                    logger.info(f"   ✓ Update SystemSetting: {row['key']} = {row['value']}")
                else:
                    reason = "readonly" if existing.is_readonly else "already exists"
                    logger.info(f"   - Skip SystemSetting ({reason}): {row['key']}")
            else:
                db.add(SystemSetting(**row))
                logger.info(f"   + Create SystemSetting: {row['key']} = {row['value']}")

    def _seed_i18n(self, db: Session, force: bool):
        """Seed I18n rows (LLM prompts + all UI text groups)."""
        logger.info("📝 Seeding I18n table...")
        files = ["i18n.json","i18n_prompt.json"]
        for f in files:
            for row in _load(f):
                existing = db.query(I18n).filter_by(
                    group=row["group"],
                    key=row["key"],
                    lang=row["lang"],
                ).first()
                if existing:
                    if force:
                        existing.value       = row["value"]
                        existing.description = row.get("description")
                        logger.info(
                            f"   ✓ Update I18n: [{row['lang']}] {row['group']}/{row['key']}"
                        )
                    else:
                        logger.info(
                            f"   - Skip I18n: [{row['lang']}] {row['group']}/{row['key']}"
                        )
                else:
                    db.add(I18n(
                        group       = row["group"],
                        key         = row["key"],
                        lang        = row["lang"],
                        value       = row["value"],
                        description = row.get("description"),
                    ))
                    logger.info(
                        f"   + Create I18n: [{row['lang']}] {row['group']}/{row['key']}"
                    )

    def _seed_strategy_config(self, db: Session, force: bool):
        """
        Seed StrategyConfig rows.
        Resolves "_kb_name" → knowledge_base.id.
        """
        logger.info("📝 Seeding strategy configs...")
        for raw in _load("strategy_config.json"):
            row = _strip_meta(raw)

            kb_name = raw.get("_kb_name")
            if not kb_name:
                logger.warning(
                    "   ⚠️ strategy_config.json record missing '_kb_name', skipping"
                )
                continue

            kb = db.query(KnowledgeBase).filter_by(name=kb_name).first()
            if not kb:
                logger.warning(
                    f"   ⚠️ KnowledgeBase '{kb_name}' not found, skipping StrategyConfig"
                )
                continue
            row["kb_id"] = kb.id

            existing = db.query(StrategyConfig).filter_by(
                kb_id=kb.id,
                version=row["version"],
            ).first()
            if existing:
                if force:
                    for k, v in row.items():
                        if k not in ("config_id", "kb_id", "version"):
                            setattr(existing, k, v)
                    logger.info(f"   ✓ Update StrategyConfig: {row['config_id']}")
                else:
                    logger.info(f"   - Skip StrategyConfig: {row['config_id']}")
            else:
                db.add(StrategyConfig(**row))
                logger.info(f"   + Create StrategyConfig: {row['config_id']}")

    def _seed_agent(self, db: Session, force: bool):
        """
        Seed Agent rows.
        Resolves "_llm_provider_name" + "_llm_model_name" → llm.id.
        """
        logger.info("📝 Seeding agents...")
        for raw in _load("agent.json"):
            row = _strip_meta(raw)

            llm_name = raw.get("_llm_name")
            if llm_name:
                llm = db.query(LLM).filter_by(
                    name=llm_name,
                ).first()
                if llm:
                    row["llm_id"] = llm.id
                else:
                    logger.warning(
                        f"   ⚠️ LLM '{llm_name}' not found "
                        f"for Agent '{row['name']}', skipping"
                    )
                    continue

            existing = db.query(Agent).filter_by(name=row["name"]).first()
            if existing:
                if force:
                    for k, v in row.items():
                        if k != "name":
                            setattr(existing, k, v)
                    logger.info(f"   ✓ Update Agent: {row['name']}")
                else:
                    logger.info(f"   - Skip Agent: {row['name']}")
            else:
                db.add(Agent(**row))
                logger.info(f"   + Create Agent: {row['name']}")   

    def _seed_role(self, db: Session, force: bool):
        logger.info("📝 Seeding roles...")
        for raw in _load("role.json"):
            row = _strip_meta(raw)
            existing = db.query(Role).filter_by(code=row["code"]).first()
            if existing:
                if force:
                    for k, v in row.items():
                        if k != "code":
                            setattr(existing, k, v)
                    logger.info(f"   ✓ Update Role: {row['code']}")
                else:
                    logger.info(f"   - Skip Role: {row['code']}")
            else:
                db.add(Role(**row))
                logger.info(f"   + Create Role: {row['code']}")

    def _seed_permission(self, db: Session, force: bool):
        logger.info("📝 Seeding permissions...")
        for raw in _load("permission.json"):
            row = _strip_meta(raw)
            existing = db.query(Permission).filter_by(code=row["code"]).first()
            if existing:
                if force:
                    for k, v in row.items():
                        if k != "code":
                            setattr(existing, k, v)
                    logger.info(f"   ✓ Update permission: {row['code']}")
                else:
                    logger.info(f"   - Skip permission: {row['code']}")
            else:
                db.add(Permission(**row))
                logger.info(f"   + Create permission: {row['code']}")

    def _seed_user_agent_relation(self, db: Session, force: bool):

        logger.info("📝 Seeding user agent relation...")
        for raw in _load("user_agent_relation.json"):
            row = _strip_meta(raw)

            agent_name = raw.get("_agent_name")
            if agent_name:
                agent = db.query(Agent).filter_by(
                    name=agent_name
                ).first()
                if agent:
                    row["agent_id"] = agent.id
                else:
                    logger.warning(
                        f"   ⚠️ UserAgentRelation agent_id not found "
                        f"for UserAgentRelation '{row['agent_name']}', skipping"
                    )
                    continue
            username = raw.get("_username")
            if username:
                user = db.query(User).filter_by(
                    username=username
                ).first()
                if user:
                    row["user_id"] = user.id
                else:
                    logger.warning(
                        f"   ⚠️ UserAgentRelation user_id not found "
                        f"for UserAgentRelation '{row['username']}', skipping"
                    )
                    continue

            existing = db.query(UserAgentRelation).filter_by(
                user_id=row["user_id"],
                agent_id=row["agent_id"]).first()
            if existing:
                if force:
                    for k, v in row.items():
                        if k not in ("user_id", "agent_id"):
                            setattr(existing, k, v)
                    logger.info(f"   ✓ Update UserAgentRelation: {row['agent_id']} , {row['user_id']}")
                else:
                    logger.info(f"   - Skip UserAgentRelation: {row['agent_id']} , {row['user_id']}")
            else:
                db.add(UserAgentRelation(**row))
                logger.info(f"   + Create UserAgentRelation: {row['agent_id']} , {row['user_id']}")

    def _seed_agent_tool_relation(self, db: Session, force: bool):

        logger.info("📝 Seeding agent tool relation...")
        for raw in _load("agent_tool_relation.json"):
            row = _strip_meta(raw)

            agent_name = raw.get("_agent_name")
            if agent_name:
                agent = db.query(Agent).filter_by(
                    name=agent_name
                ).first()
                if agent:
                    row["agent_id"] = agent.id
                else:
                    logger.warning(
                        f"   ⚠️ AgentToolRelation agent_id not found "
                        f"for AgentToolRelation '{row['agent_name']}', skipping"
                    )
                    continue

            tool_name = raw.get("_tool_name")
            if tool_name:
                tool = db.query(Tool).filter_by(
                    name=tool_name
                ).first()
                if tool:
                    row["tool_id"] = tool.id
                else:
                    logger.warning(
                        f"   ⚠️ AgentToolRelation tool_id not found "
                        f"for AgentToolRelation '{row['tool_name']}', skipping"
                    )
                    continue

            existing = db.query(AgentToolRelation).filter_by(
                tool_id=row["tool_id"],
                agent_id=row["agent_id"]).first()
            if existing:
                if force:
                    for k, v in row.items():
                        if k not in ("tool_id", "agent_id"):
                            setattr(existing, k, v)
                    logger.info(f"   ✓ Update AgentToolRelation: {row['agent_id']} , {row['tool_id']}")
                else:
                    logger.info(f"   - Skip AgentToolRelation: {row['agent_id']} , {row['tool_id']}")
            else:
                db.add(AgentToolRelation(**row))
                logger.info(f"   + Create AgentToolRelation: {row['agent_id']} , {row['tool_id']}")

    def _seed_role_permission_relation(self, db: Session, force: bool):

        logger.info("📝 Seeding role permission relation...")
        for raw in _load("role_permission_relation.json"):
            row = _strip_meta(raw)

            role_code = raw.get("_role_code")
            if role_code:
                role = db.query(Role).filter_by(
                    code=role_code
                ).first()
                if role:
                    row["role_id"] = role.id
                else:
                    logger.warning(
                        f"   ⚠️ RolePermissionRelation role_id not found "
                        f"for RolePermissionRelation '{row['role_code']}', skipping"
                    )
                    continue

            permission_code = raw.get("_permission_code")
            if permission_code:
                permission = db.query(Permission).filter_by(
                    code=permission_code
                ).first()
                if permission:
                    row["permission_id"] = permission.id
                else:
                    logger.warning(
                        f"   ⚠️ RolePermissionRelation permission_id not found "
                        f"for RolePermissionRelation '{row['permission_code']}', skipping"
                    )
                    continue

            existing = db.query(RolePermissionRelation).filter_by(
                permission_id=row["permission_id"],
                role_id=row["role_id"]).first()
            if existing:
                if force:
                    for k, v in row.items():
                        if k not in ("permission_id", "role_id"):
                            setattr(existing, k, v)
                    logger.info(f"   ✓ Update RolePermissionRelation: {row['role_id']} , {row['permission_id']}")
                else:
                    logger.info(f"   - Skip RolePermissionRelation: {row['role_id']} , {row['permission_id']}")
    
    def _seed_user_role_relation(self, db: Session, force: bool = False):
        logger.info("📝 Seeding user role relation...")
        for raw in _load("user_role_relation.json"):
            row = _strip_meta(raw)

            username = raw.get("_username")
            if username:
                user = db.query(User).filter_by(
                    username=username
                ).first()
                if user:
                    row["user_id"] = user.id
                else:
                    logger.warning(
                        f"   ⚠️ UserRoleRelation user_id not found "
                        f"for UserRoleRelation '{row['username']}', skipping"
                    )
                    continue

            role_code = raw.get("_role_code")
            if role_code:
                role = db.query(Role).filter_by(
                    code=role_code
                ).first()
                if role:
                    row["role_id"] = role.id
                else:
                    logger.warning(
                        f"   ⚠️ UserRoleRelation role_id not found "
                        f"for UserRoleRelation '{row['role_code']}', skipping"
                    )
                    continue

            existing = db.query(UserRoleRelation).filter_by(
                user_id=row["user_id"],
                role_id=row["role_id"]).first()
            if existing:
                if force:
                    for k, v in row.items():
                        if k not in ("user_id", "role_id"):
                            setattr(existing, k, v)
                    logger.info(f"   ✓ Update UserRoleRelation: {row['user_id']} , {row['role_id']}")
                else:
                    logger.info(f"   - Skip UserRoleRelation: {row['user_id']} , {row['role_id']}")
            else:
                db.add(UserRoleRelation(**row))
                logger.info(f"   + Create UserRoleRelation: {row['user_id']} , {row['role_id']}")

    def get_session(self) -> Session:
        """Return a new database session."""
        return self.SessionLocal()


# ═══════════════════════════════════════════════════════════════════════════
# Application startup helper
# ═══════════════════════════════════════════════════════════════════════════

db_manager = DatabaseManager()


def init_database_on_startup(force_rebuild: bool = False, seed_data: bool = True) -> bool:
    logger.info("=" * 60)
    logger.info("🚀 Database initialization")
    logger.info("=" * 60)

    db_exists = db_manager.check_database()

    if not db_exists or force_rebuild:
        success = db_manager.init_database(force=force_rebuild)
        if not success:
            logger.error("❌ Database initialization failed.")
            return False
        if seed_data:
            success = db_manager.seed_data(force=force_rebuild)
            if not success:
                logger.warning("⚠️ Preset data population failed, but the database was created.")
    else:
        logger.info("✅ The database already exists.")
        db_manager.upgrade_schema()
        if seed_data:
            db_manager.seed_data(force=False)

    logger.info("=" * 60)
    logger.success("✅ Database preparation complete")
    logger.info("=" * 60)
    return True


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Database management tools")
    parser.add_argument(
        "command",
        choices=["init", "check", "reset", "seed", "upgrade"],
        help=(
            "init: create tables + seed  |  check: verify  |  "
            "reset: drop + recreate  |  seed: (re)populate data  |  "
            "upgrade: add missing tables"
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite of existing data (used with reset and seed)",
    )
    args = parser.parse_args()

    if args.command == "init":
        db_manager.init_database(force=False)
        db_manager.seed_data(force=False)

    elif args.command == "check":
        db_manager.check_database()

    elif args.command == "reset":
        if args.force:
            confirm = input("⚠️ Reset will delete ALL data. Type 'yes' to confirm: ")
            if confirm.strip().lower() == "yes":
                db_manager.init_database(force=True)
                db_manager.seed_data(force=True)
            else:
                logger.info("❌ Operation cancelled")
        else:
            logger.warning("⚠️ Reset requires --force.")

    elif args.command == "seed":
        db_manager.seed_data(force=args.force)

    elif args.command == "upgrade":
        db_manager.upgrade_schema()

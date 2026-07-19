#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-07
# @description: SQLite data model definition, Define the data table structure using SQLAlchemy ORM

from datetime import datetime
from sqlalchemy import CheckConstraint, Column, Index, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship,validates

Base = declarative_base()

class User(Base):
    """Users model"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True,autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, comment="Username")
    password_hash = Column(String(255), nullable=False, comment="Password hash")

    nickname     = Column(String(100), nullable=True,  comment="Display nickname")
    avatar       = Column(String(500), nullable=True,  comment="Avatar URL")

    created_at = Column(DateTime, default=lambda: datetime.now())
    last_login = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)    
    roles = relationship("Role", secondary="user_role_relations", back_populates="users")
    agents = relationship("Agent", secondary="user_agent_relations", back_populates="users")
    
    def __repr__(self):
        return f"<User(user_id='{self.id}')>"

class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_super = Column(Boolean, default=False)

    users = relationship("User", secondary="user_role_relations", back_populates="roles")    
    menus = relationship("Menu", secondary="role_menu_relations", back_populates="roles")

    def __repr__(self):
        return f"<Role(role_id='{self.id}')>"

class UserRoleRelation(Base):
    __tablename__ = "user_role_relations"

    user_id = Column(ForeignKey("users.id"), primary_key=True)
    role_id = Column(ForeignKey("roles.id"), primary_key=True)

    def __repr__(self):
        return f"<UserRoleRelation(user_id='{self.user_id}', role_id='{self.role_id}')>"

class Menu(Base):
    __tablename__ = "menus"

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("menus.id"), nullable=True)

    name = Column(String(100), nullable=False)
    title_key = Column(String(100), nullable=False)
    path = Column(String(200))
    component = Column(String(200))
    icon = Column(String(100))
    sort_order = Column(Integer, default=0)
    menu_type = Column(String(20),nullable=False,default="menu",comment="menu/button")
    description = Column(Text, nullable=True)

    is_visible = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("parent_id", "name"),
    )

    parent = relationship(
        "Menu",
        remote_side=[id],
        back_populates="children"
    )

    children = relationship(
        "Menu",
        back_populates="parent",
        cascade="all, delete-orphan"
    )

    roles = relationship("Role", secondary="role_menu_relations", back_populates="menus")

    def __repr__(self):
        return f"<Menu(id='{self.id}', name='{self.name}')>"

class RoleMenuRelation(Base):
    __tablename__ = "role_menu_relations"

    role_id = Column(ForeignKey("roles.id"), primary_key=True)
    menu_id = Column(ForeignKey("menus.id"), primary_key=True)

    def __repr__(self):
        return f"<RoleMenuRelation(role_id='{self.role_id}', menu_id='{self.menu_id}')>"
    
class LLM(Base):
    """LLM model"""
    __tablename__ = "llms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, comment="LLM Name")
    provider_name = Column(String(50), nullable=False)
    base_url = Column(String(1024), nullable=False)
    api_key = Column(String(512), nullable=True, comment="API key (optional for local models)")
    model_name = Column(String(100), nullable=False)
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=2000)
    capabilities = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now())

    __table_args__ = (
        UniqueConstraint("provider_name", "model_name", name="uq_provider_model"),
        Index("idx_provider_name", "provider_name"),
    )

    agents = relationship("Agent", back_populates="llm")
    knowledge_bases = relationship("KnowledgeBase", back_populates="llm")

    def __repr__(self):
        return f"<LLM(provider='{self.provider_name}', model='{self.model_name}')>"

class Agent(Base):

    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, comment="Agent Name")
    description = Column(Text, nullable=True, comment="Agent Description")
    system_prompt = Column(Text, nullable=False, comment="System Prompt")
    llm_id = Column(Integer, ForeignKey("llms.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())
    is_active = Column(Boolean, default=True, comment="Activate or not?")

    __table_args__ = (
        Index("idx_agent_llm_id", "llm_id"),
        Index("idx_agent_is_active", "is_active"),
        UniqueConstraint("name", name="uq_agent_name")
    )

    llm = relationship("LLM", back_populates="agents")
    users = relationship("User", secondary="user_agent_relations", back_populates="agents")    
    tools = relationship("Tool", secondary="agent_tool_relations", back_populates="agents")    
    chat_sessions = relationship("ChatSession", back_populates="agent")

    def __repr__(self):
        return f"<Agent(name='{self.name}')>"

class ChatSession(Base):
    """Chat Session"""
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), comment="title")
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)

    # Statistical information
    message_count = Column(Integer, default=0, comment="Message Count")

    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    __table_args__ = (        
        Index("idx_user_id", "user_id"),
    )

    user = relationship("User", back_populates="chat_sessions")
    agent = relationship("Agent", back_populates="chat_sessions")  
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan", passive_deletes=True) 

    def __repr__(self):
        return f"<ChatSession(user_id='{self.user_id}', session_id='{self.id}')>"


class ChatMessage(Base):
    """Chat Message"""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)    
    session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)

    role = Column(String(20), nullable=False, comment="user / assistant / system")
    content = Column(Text, nullable=False)  

    created_at = Column(DateTime, default=lambda: datetime.now())

    __table_args__ = (
        Index("idx_session_created", "session_id", "created_at"),
    )

    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self):
        return f"<ChatMessage(id={self.id}, role='{self.role}')>"

class UserAgentRelation(Base):
    """User-Agent Association Table"""
    __tablename__ = "user_agent_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now())

    __table_args__ = (
        UniqueConstraint("user_id", "agent_id", name="uq_user_agent"),
    )

    def __repr__(self):
        return f"<UserAgentRelation(user_id={self.user_id}, agent_id={self.agent_id})>"


class Embedding(Base):
    __tablename__ = "embeddings"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True)
    provider_name = Column(String(50), nullable=False, comment="Embedding provider name, e.g., openai, local, etc.")
    base_url = Column(String(1024), nullable=False)
    api_key = Column(String(512), nullable=True, comment="API key (optional for local models)")
    model_name = Column(String(100), nullable=False)
    max_tokens = Column(Integer, default=512)

    created_at = Column(DateTime, default=lambda: datetime.now())

    knowledge_bases = relationship("KnowledgeBase", back_populates="embedding")

    def __repr__(self):
        return f"<Embedding(provider='{self.provider_name}', model='{self.model_name}')>"

class Domain(Base):
    """
    Domain model — represents a knowledge domain (e.g. general, law, medical).    
    """
    __tablename__ = "domains"

    id          = Column(Integer,     primary_key=True, autoincrement=True)
    name        = Column(String(50),  nullable=False, unique=True,
                         comment="Domain identifier, e.g. company_law_cn / labor_contract_law_cn")
    type = Column(String(50),  nullable=False, comment="Domain type, e.g. general / law / doctor")
    processor_class = Column(String(100),  nullable=False, comment="Fully named processor class")
    plugin_class = Column(String(100),  nullable=False, comment="Fully named plugin class")
    description = Column(Text,        nullable=True,
                         comment="Human-readable description shown in the UI")
    metadata_schema = Column(JSON,    nullable=True,
                         comment="JSON Schema for domain-specific document metadata fields; "
                                 "drives the dynamic upload form in the UI")

    created_at  = Column(DateTime, default=lambda: datetime.now())
    updated_at  = Column(DateTime, default=lambda: datetime.now(),
                         onupdate=lambda: datetime.now())

    knowledge_bases = relationship("KnowledgeBase", back_populates="domain")

    def __repr__(self):
        return f"<Domain(name='{self.name}')>"

class KnowledgeBase(Base):
    """Knowledge base model"""
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)    
    domain_id = Column(Integer, ForeignKey("domains.id", ondelete="RESTRICT"), nullable=False,
                       comment="Domain this KB belongs to — determines the DomainPlugin used at indexing time")
    keywords = Column(
        JSON,
        nullable=True,
        comment="List of keywords for SmartRouter keyword matching, e.g. ['合同', '劳动法', '离职']"
    )
    description = Column(Text, nullable=True, comment="Knowledge base description")

    collection_name = Column(String(100), nullable=False, unique=True, comment="VectorDB collection name,one kb->one collection")
    embedding_id = Column(Integer,ForeignKey("embeddings.id", ondelete="SET NULL"),nullable=True)
    # Document statistics
    document_count = Column(Integer, default=0, comment="Number of documents")    
    chunk_count = Column(Integer, default=0, comment="Number of blocks")

    # ── Chunking parameters (per-KB, independently tunable) ──────────────────
    # These intentionally remain on KnowledgeBase rather than on Domain.
    # Two KBs in the same domain (e.g. one for full-text retrieval, one for
    # Q&A) may need very different window sizes; Domain is for identity and
    # routing, not for numeric tuning.
    chunk_size = Column(Integer, default=400, comment="Block size (number of characters)")
    chunk_overlap = Column(Integer, default=80, comment="Block overlap (number of characters)")
    parent_size = Column(Integer, default=1800, comment="Parent block size (number of characters)")
    parent_overlap = Column(Integer, default=200, comment="Parent block overlap (number of characters)")

    llm_id = Column(Integer, ForeignKey("llms.id", ondelete="SET NULL"), nullable=True)

    # timestamps
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())
    is_active = Column(Boolean, default=True, comment="Activate or not?")

    __table_args__ = (
        Index("idx_kb_embedding_id", "embedding_id"),
        Index("idx_kb_is_active", "is_active"),
        Index("idx_kb_domain_id", "domain_id"),
        Index("idx_kb_llm_id", "llm_id"),
    )

    domain = relationship("Domain", back_populates="knowledge_bases")    
    documents = relationship("Document", back_populates="knowledge_base", cascade="all, delete-orphan", passive_deletes=True)
    embedding = relationship("Embedding", back_populates="knowledge_bases")    
    strategy_configs = relationship("StrategyConfig", back_populates="knowledge_base", cascade="all, delete", passive_deletes=True)
    llm = relationship("LLM", back_populates="knowledge_bases")

    def __repr__(self):
        return f"<KnowledgeBase(name='{self.name}')>"
class SystemSetting(Base):
    """
    Singleton-style key-value store for global system configuration.
    """
    __tablename__ = "system_settings"

    key         = Column(String(100), primary_key=True,  comment="Setting key, e.g. 'system_language'")
    value       = Column(Text,        nullable=False,     comment="Setting value (always stored as string)")
    value_type  = Column(String(20),  nullable=False, default="string",
                         comment="Hint for UI rendering / type coercion: string | int | float | bool | json")
    group       = Column(String(50),  nullable=False, default="general",
                         comment="UI section grouping, e.g. general / retrieval / appearance")
    description = Column(Text,        nullable=True,  comment="Developer-facing description")
    is_readonly = Column(Boolean,     default=False,  comment="True → shown in UI but not editable by admins")

    updated_at  = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    __table_args__ = (
        Index("idx_settings_group", "group"),
    )

    def __repr__(self):
        return f"<SystemSetting(key='{self.key}', value='{self.value}')>"

class Prompt(Base):
    __tablename__ = "prompts"

    id          = Column(Integer,     primary_key=True, autoincrement=True)    
    key         = Column(String(200), nullable=False, comment="Identifier within the group, e.g. 'query_rewrite'.")
    lang        = Column(String(10),  nullable=False, comment="language tag, lower-cased, e.g. zh_CN / en_US")
    value       = Column(Text,        nullable=False, comment="Translated string; prompt group supports {placeholder} variables")
    description = Column(String(255), nullable=True,  comment="Developer / admin note, not shown to end users")

    created_at  = Column(DateTime, default=lambda: datetime.now())
    updated_at  = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    __table_args__ = (
        UniqueConstraint("key", "lang", name="uq_prompt_group_key_lang"),
        Index("idx_prompt_lang",       "lang"),
    )

    def __repr__(self):
        return f"<Prompt(key='{self.key}', lang='{self.lang}')>"


class StrategyConfig(Base):
    __tablename__ = "strategy_configs"

    config_id = Column(String(100), primary_key=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)

    version = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=False)

    # Component switches
    enable_query_rewrite = Column(Boolean, default=True)
    enable_query_expansion = Column(Boolean, default=False)
    enable_query_hyde = Column(Boolean, default=False)
    enable_vector = Column(Boolean, default=True)
    enable_bm25 = Column(Boolean, default=True)
    enable_reranker = Column(Boolean, default=True)    
    enable_small_to_big = Column(Boolean, default=True)
    require_citation = Column(Boolean, default=True, comment="Mandatory source tracing?")

    # Search parameters
    query_expansion_num = Column(Integer, default=3)
    max_transform_queries = Column(Integer, default=5)
    vector_top_k = Column(Integer, default=30, comment="Number of top-k retrievals")
    bm25_top_k = Column(Integer, default=30, comment="Number of bm25 retrievals")
    rrf_mode = Column(String(20), default="rrf", comment="rrf,weighted")
    rrf_k = Column(Integer, default=60, comment="k value when rrf_mode == rrf")
    rrf_top_k = Column(Integer, default=20)
    vector_weight = Column(Float, default=0.6, comment="vector weight when rrf_mode == weighted")
    reranking_mode = Column(String(20), default="hybrid", comment="vector,bm25,hybrid,rerank,llm")
    rerank_top_k = Column(Integer, default=10)
    final_top_k = Column(Integer, default=3)

    # Threshold parameters
    vector_score_threshold = Column(Float, default=0.5, comment="Similarity threshold (0-1, the higher the threshold, the stricter the similarity).")
    bm25_score_threshold = Column(Float, default=0.1)

    # Confidence
    confidence_high_score_threshold = Column(Float, default=0.7)
    confidence_min_high_conf_count = Column(Integer, default=1, comment="At least several high-scoring results are needed to be considered high confidence.")
    confidence_low_score_threshold = Column(Float, default=0.5)

    # Additional configuration, such as: ranking_weights
    extra_config = Column(JSON, comment="Extended configuration in JSON format")

    created_at = Column(DateTime, default=lambda: datetime.now())
    created_by = Column(String(100))

    knowledge_base = relationship("KnowledgeBase", back_populates="strategy_configs")

    __table_args__ = (
        UniqueConstraint("kb_id", "version", name="uq_kb_version"),
        Index("idx_strategy_kb_active", "kb_id", "is_active"),
        CheckConstraint("vector_score_threshold >= 0 AND vector_score_threshold <= 1", name="ck_vector_score_threshold_range"),
        CheckConstraint("vector_top_k > 0", name="ck_vector_top_k_positive"),
        CheckConstraint("bm25_top_k > 0", name="ck_bm25_top_k_positive"),
    )

class Document(Base):
    """Document Model"""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Document ID")
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)

    hash_value = Column(String(64), nullable=False, comment="Document hash value (SHA-256)")
    filename = Column(String(255), nullable=False, comment="file name")
    mime_type = Column(String(50), nullable=False, comment="file type")
    file_size = Column(Integer, comment="File size (bytes)")
    file_uri  = Column(String(1024), nullable=True, comment="File storage URI (local path or cloud URL)")
    storage_type = Column(String(20), default="local", comment="Storage type: local or cloud") 

    chunk_count = Column(Integer, default=0, comment="Number of blocks")
    meta_data_json = Column(JSON, nullable=True, comment="metadata information,JSON format string")

    status = Column(String(20), default="pending", comment="Processing status: pending, processing, completed, failed")
    error_message = Column(Text, nullable=True, comment="error message if processing failed")

    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())

    __table_args__ = (
        Index("idx_kb_id", "kb_id"),
        Index("idx_kb_status", "kb_id", "status"),
        Index("idx_kb_hash", "kb_id", "hash_value"),        
        UniqueConstraint("kb_id", "hash_value")
    )

    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    parent_chunks = relationship("ParentChunk", back_populates="document", cascade="all, delete-orphan")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Document(id={self.id}, filename='{self.filename}')>"

class ParentChunk(Base):
    """Parent Chunk（Small-to-Big）"""
    __tablename__ = "parent_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    doc_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    hash_value = Column(String(64), nullable=False, comment="Chunk hash value (SHA-256)")

    text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)

    char_count = Column(Integer, nullable=False)
    token_count = Column(Integer,nullable=False,default=0, comment="Number of tokens in the chunk")

    created_at = Column(DateTime, default=lambda: datetime.now())

    __table_args__ = (
        Index("idx_parent_doc", "doc_id"),
        Index("idx_parent_kb", "kb_id"),
        Index("idx_parent_hash", "kb_id", "hash_value"),
        UniqueConstraint("doc_id","chunk_index",name="uq_parent_doc_chunk")
    )

    document = relationship("Document", back_populates="parent_chunks")
    chunks = relationship("Chunk", back_populates="parent", cascade="all, delete-orphan", passive_deletes=True)

class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)

    kb_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    doc_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(Integer, ForeignKey("parent_chunks.id", ondelete="CASCADE"), nullable=False)
    hash_value = Column(String(64), nullable=False, comment="Chunk hash value (SHA-256)")

    text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    token_count = Column(Integer,nullable=False,default=0, comment="Number of tokens in the chunk")

    char_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now())

    __table_args__ = (
        Index("idx_chunk_doc", "doc_id"),
        Index("idx_chunk_parent", "parent_id"),
        Index("idx_chunk_kb", "kb_id"),
        Index("idx_chunk_hash", "kb_id", "hash_value"),
        Index("idx_chunk_doc_chunk", "doc_id", "chunk_index"),
        UniqueConstraint("parent_id","chunk_index",name="uq_chunk_parent_chunk")
    )

    document = relationship("Document", back_populates="chunks")
    parent = relationship("ParentChunk", back_populates="chunks")

VALID_SELECTION_STRATEGIES = {"keyword", "embedding"}

class RouterConfig(Base):
    __tablename__ = "router_configs"

    config_id = Column(String(100), primary_key=True)
    selection_strategy = Column(String(20), nullable=False,default="embedding",comment="KB Selection Strategy, include: keyword | embedding")
    
    fallback_to_all = Column(Boolean, nullable=False,default=True,comment="If no knowledge base is selected, do you want to query all knowledge bases?")
    max_kb_count = Column(Integer, nullable=False,default=3,comment="Maximum KB limit (to prevent explosion)")

    extra_config = Column(JSON,nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now())

    @validates("selection_strategy")
    def validate_strategy(self, key: str, value: str) -> str:
        if value not in VALID_SELECTION_STRATEGIES:
            raise ValueError(
                f"selection_strategy must be within {VALID_SELECTION_STRATEGIES},got: {value!r}"
            )
        return value
   
    def __repr__(self) -> str:
        return (
            f"<RouterConfig(config_id={self.config_id!r}, "
            f"strategy={self.selection_strategy!r})>"
        )

VALID_TOOL_TYPES = {"function", "api", "smart_router","sql_agent"}

class Tool(Base):
 
    __tablename__ = "tools"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True)
    description = Column(Text, comment="tool description")
    tool_type = Column(String(50), nullable=False,default="function", comment="Tool type: function | api | smart_router | sql_agent")

    tool_schema = Column(JSON, nullable=False, comment="Tool definition(JSON Schema format)")    
    config = Column(JSON, comment="Tool configuration, JSON format string")

    created_at = Column(DateTime, nullable=False,default=lambda: datetime.now())
    updated_at = Column(DateTime, nullable=False,default=lambda: datetime.now(), onupdate=lambda: datetime.now())
    is_active = Column(Boolean, nullable=False,default=True, comment="Activate or not?")

    agents = relationship("Agent", secondary="agent_tool_relations", back_populates="tools")

    __table_args__ = (
        Index("ix_tool_type_active", "tool_type", "is_active"),
    )

    @validates("tool_type")
    def validate_tool_type(self, key: str, value: str) -> str:
        if value not in VALID_TOOL_TYPES:
            raise ValueError(
                f"tool_type must be within {VALID_TOOL_TYPES}, got: {value!r}"
            )
        return value

    def __repr__(self):
        return (
            f"<Tool(name={self.name!r}, type={self.tool_type!r}, "
            f"active={self.is_active})>"
        )


class AgentToolRelation(Base):
    __tablename__ = "agent_tool_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    tool_id = Column(Integer, ForeignKey("tools.id", ondelete="CASCADE"), nullable=False)

    priority = Column(Integer, default=0, comment="Priority,the smaller the number, the higher the priority.")
    config_override = Column(JSON, comment="Tool configuration override for this agent, JSON format string")
    created_at = Column(DateTime, default=lambda: datetime.now())

    __table_args__ = (
        UniqueConstraint("agent_id", "tool_id", name="uq_agent_tool"),
    )

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(36), nullable=False, comment="Request correlation ID (UUID)")
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    username = Column(String(100), nullable=True)
    ip_address = Column(String(50), nullable=True)

    target_type = Column(String(50), nullable=False, comment="Module name, such as 'KnowledgeBase', 'Agent'")
    target_id = Column(String(100), nullable=False, comment="Target object ID")

    action = Column(String(20), nullable=False, comment="Operation type:CREATE, UPDATE, DELETE, EXECUTE")
    before_value = Column(JSON, nullable=True, comment="Snapshot of data before modification")
    after_value = Column(JSON, nullable=True, comment="Snapshot of data after modification")

    description = Column(Text, nullable=True, comment="Operation description, e.g., 'Updated knowledge base chunking strategy'")
    status = Column(String(20), default="success", comment="Operation result: success, failure")
    
    created_at = Column(DateTime, default=lambda: datetime.now())

    __table_args__ = (
        Index("idx_audit_request", "request_id"),
        Index("idx_audit_target", "target_type", "target_id"),
        Index("idx_audit_user", "user_id"),
        Index("idx_audit_created", "created_at"),
    )


class LoginLog(Base):
    __tablename__ = "login_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(36), nullable=False, comment="Request correlation ID (UUID)")

    event_type = Column(
        String(20),
        nullable=False,
        comment="Authentication event: LOGIN | REFRESH_TOKEN",
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    username = Column(String(100), nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(Text, nullable=True)

    success = Column(Boolean, nullable=False, default=False)
    failure_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now())

    __table_args__ = (
        Index("idx_login_request", "request_id"),
        Index("idx_login_user", "user_id"),
        Index("idx_login_event", "event_type", "success"),
        Index("idx_login_created", "created_at"),
    )

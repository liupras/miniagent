# MiniAgent - admin lightweight agent platform

**MiniAgent** is a lightweight agent platform (Chinese/English) for individuals and small teams. The backend is a FastAPI app that manages agents, knowledge bases, tools, LLM configs, auth/RBAC, and runtime features (RAG retrieval, SQL agent, web search). The frontend lives in management/ (vue-pure-admin).

## High-level architecture

~~~mermaid
flowchart TB
    subgraph HTTP
        API["app/api/*"]
    end
    subgraph Core
        SC["ServiceContainer<br/>app/core/service_container.py"]
        CFG["Settings<br/>app/core/config.py"]
    end
    subgraph Runtime
        AF["AgentFactory"]
        AR["AgentRunner<br/>LangChain"]
        TB["ToolBuilder"]
    end
    subgraph KB
        DOC["KBDocumentService"]
        RET["KBRetrievalService"]
        SR["KBSmartRouterService"]
        VS["VectorStore + BM25"]
    end
    subgraph Data
        REPO["repositories/async_*"]
        SQLITE[(SQLite)]
        CHROMA[(ChromaDB)]
        DUCK[(DuckDB)]
    end

    API --> SC
    SC --> AF --> AR
    AF --> TB
    SC --> DOC & RET & SR
    RET --> VS
    REPO --> SQLITE
    VS --> CHROMA
    SC --> DUCK
~~~

**Layering convention** (follow this when adding features):

- app/api/ — HTTP only: routing, request/response models, Depends() wiring
- app/services/ — Business logic
- app/repositories/ — Async DB access (Async*Database classes)
- app/schemas/ — Pydantic request/response DTOs
- app/infra/ — DB models, LLM helpers, prompts, cache
API responses usually use the envelope in app/schemas/common.py:

~~~python
ApiResponse(data=...)  # { code: 200, message: "success", data: ... }
~~~

## Startup sequence

~~~python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    # ...
    init_database_on_startup(force_rebuild=False, seed_data=True)
    # ...
    app.state.container = ServiceContainer()
    await app.state.container.start()
~~~

**On boot**:

- DB init — app/infra/db/initializer.py creates SQLite tables and loads seed JSON from app/infra/db/seed/
- ServiceContainer — builds async SQLAlchemy engine, all repositories, and long-lived services
- Domain plugins — loads Domain rows from DB and registers KB processors via dynamic import

Everything shared lives on request.app.state.container. Routes get it via Depends(get_container).

## Main entry points

### 1. Application root — `app/main.py`
CORS, request logging, global exception handler
Registers all API routers under /api/v1/...
Ops routes: /, /health, /config (debug), /db/info
### 2. Configuration — `app/core/config.py`
Pydantic Settings from .env: SQLite/DuckDB/Chroma paths, JWT, CORS, log level, token limits.

Required: JWT_SECRET_KEY (no default in code).

### 3. Dependency hub — `app/core/service_container.py`

### 4. Data models — `app/infra/db/database.py`
SQLAlchemy ORM for users, roles, menus, agents, tools, LLMs, embeddings, knowledge bases, documents/chunks, chat sessions, router configs, domains, etc.

## Knowledge base pipeline

~~~text
Upload → DomainPlugin (general / law_cn) → chunk → embed → Chroma + BM25
Query  → RetrievalPipeline (vector + BM25 + RRF + optional reranker)
Multi-KB → SmartRouter (router config from DB)
~~~

Domains are configured in seed data and registered at startup:
~~~text
"processor_class":"app.services.kb.SmallToBigProcessor",
"plugin_class":"app.services.kb.GeneralDomainPlugin",
~~~

## Other skills
- SQL Agent — app/services/sql_agent/: DuckDB manager, sandboxed execution, schema context
- Web Search — app/services/skill/: search service + LangChain tool wrapper
- Storage — app/storage/: local file backend for uploaded documents

## What to read before changing things

1. app/main.py — router map and lifecycle
2. app/core/service_container.py — where to register new services
3. app/infra/db/database.py — schema
4. app/schemas/common.py — API response shape

## Singleton

- prompt_loader(app.core.prompt_loader.py)
- t,translations(app.core.I18n.I18n.py)
- cache_registry(app.infra.store_registry.py)

## Caching

### AsyncLazyCache(Memory)

- WebSearchService(web_search_pipeline) — tool_name → WebSearchPipeline 
- SQLAgentService(sql_agent) — tool_name → SQLAgent
- AgentFactory(agent_runner) — agent_id → AgentRunner
- KBRetrievalService(kb_retrieval_pipeline) — kb_id → RetrievalPipeline,kb_id → KBInfo
- SmartRouterFactory(smart_router) — router_config_id → SmartRouter
- SmartRouter(smart_router_kb_embedding) — kb_id → Embedding
- VectorStoreRegistry(vector_store_manager) — kb_id → VectorStoreManager

### CacheStoreRegistry

- AuthPermission — auth,user_perms:
- BM25Manager — bm25
- RetrievalPipeline  — retrieval
- SearchResultCache — web_search
- SchemaContextBuilder — schema_context


After DB updates, call the matching invalidate() or users see stale config. Admin services often do this already — follow that pattern.
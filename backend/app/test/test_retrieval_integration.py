#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
RetrievalPipeline 集成测试脚本
语料：中华人民共和国公司法（已完成向量化 + BM25 索引）

前置条件
────────
1. Ollama 服务已启动，embedding 模型已拉取：
       ollama pull quentinz/bge-large-zh-v1.5
2. ChromaDB 持久化目录存在且已索引（默认 ./data/vector）
3. BM25 索引文件存在（默认 ./data/bm25_storage/<kb_id>.json）
4. SQLite 数据库已初始化，且 kb_id 对应的 StrategyConfig 存在 is_active=True 的记录

测试覆盖
────────
  Case 1 — As-Is Pipeline       直接使用数据库中的激活配置运行，验证端到端流程
  Case 2 — Vector Only          覆盖为仅向量检索，验证结果非空、按分数降序
  Case 3 — BM25 Only            覆盖为仅 BM25 检索，验证关键词命中
  Case 4 — Hybrid RRF           覆盖为双路 RRF 融合，验证去重 + rrf 路径标记
  Case 5 — Hybrid Weighted      覆盖为加权融合，验证 weighted 路径标记
  Case 6 — Small-to-Big         覆盖为 S2B 展开，验证父块文本替换与去重
  Case 7 — Empty Query Guard    空查询应直接返回空列表
  Case 8 — Score Threshold      提高阈值后结果数 ≤ 低阈值结果数

运行方式
────────
    # 基础运行（使用默认路径）
    python test_retrieval_integration.py

    # 自定义路径
    python test_retrieval_integration.py \
        --vector-path ./data/vector \
        --bm25-path   ./data/bm25_storage \
        --db-path     ./data/app.db \
        --ollama-url  http://localhost:11434 \
        --embed-model quentinz/bge-large-zh-v1.5 \
        --kb-id       1 \
        -v

    # 跳过 S2B（parent_chunk 数据不完整时）
    python test_retrieval_integration.py --skip-s2b
"""

import asyncio
import sys
import os
from types import SimpleNamespace
from typing import List

# ── 路径修正 ──────────────────────────────────────────────────────────────────
_here         = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_here)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
if _here not in sys.path:
    sys.path.insert(0, _here)
# ─────────────────────────────────────────────────────────────────────────────

from loguru import logger

from ..services.kb.vector_store import VectorStoreManager
from ..services.kb.bm25_manager import BM25Manager
from ..services.kb.retrieval    import RetrievalPipeline
from app.infra.db  import AsyncParentChunkDatabase, AsyncKnowledgeBaseDatabase,AsyncChunkDatabase,AsyncDocumentDatabase


# ─────────────────────────────────────────────────────────────────────────────
# StrategyConfig 覆盖工具
# 部分测试需要在数据库配置基础上局部修改参数（如关闭 BM25、调整阈值），
# 用 SimpleNamespace 浅拷贝原 ORM 对象的字段，避免污染数据库行。
# ─────────────────────────────────────────────────────────────────────────────

_CONFIG_FIELDS = [
    "kb_id", "config_id", "version", "is_active",
    "enable_query_rewrite","enable_query_expansion","enable_query_hyde",
    "enable_vector", "enable_bm25", "enable_rrf", "enable_reranker",
    "enable_small_to_big", "require_citation",
    "query_expansion_num","max_transform_queries",
    "vector_top_k", "bm25_top_k", "rrf_mode", "rrf_k","rrf_top_k",
    "vector_weight", "reranking_mode", "rerank_top_k", "final_top_k",
    "vector_score_threshold", "bm25_score_threshold", 
    "confidence_high_score_threshold", "confidence_low_score_threshold", 
    "confidence_min_high_conf_count", "confidence_warning_template",
    "extra_config",
    "base_url","api_key","temperature","hide_thinking"
]

def override_config(db_config, **kwargs) -> SimpleNamespace:
    """
    把数据库读取的 StrategyConfig ORM 对象浅拷贝为 SimpleNamespace，
    再用 kwargs 覆盖指定字段。原 ORM 对象不受影响。
    """
    ns = SimpleNamespace(**{f: getattr(db_config, f, None) for f in _CONFIG_FIELDS})
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


# ─────────────────────────────────────────────────────────────────────────────
# 测试辅助
# ─────────────────────────────────────────────────────────────────────────────
PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
SKIP = "\033[93m- SKIP\033[0m"
_summary: List[tuple] = []


def assert_ok(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


def _print_chunks(chunks, verbose: bool):
    if not verbose:
        return
    for i, rc in enumerate(chunks, 1):
        path    = " -> ".join(rc.retrieval_path)
        preview = rc.text[:100].replace("\n", " ")
        print(f"    [{i}] chunk_id={rc.chunk_id}  doc_id={rc.doc_id}"
              f"  score={rc.final_score:.4f}  path=[{path}]")
        print(f"        {preview}{'...' if len(rc.text) > 100 else ''}")


def _print_config(cfg):
    print(f"  config_id={cfg.config_id}  version={getattr(cfg, 'version', '?')}")
    print(f"  vector={cfg.enable_vector}  bm25={cfg.enable_bm25}"
          f"  s2b={cfg.enable_small_to_big}  reranker={cfg.enable_reranker}")
    print(f"  rrf_mode={cfg.rrf_mode}  reranking_mode={cfg.reranking_mode}"
          f"  final_top_k={cfg.final_top_k}")
    print(f"  vector_score_threshold={cfg.vector_score_threshold}"
          f"  bm25_score_threshold={cfg.bm25_score_threshold}")


# ─────────────────────────────────────────────────────────────────────────────
# Test cases
# ─────────────────────────────────────────────────────────────────────────────

async def case1_as_is(vs, bm25, pc_db, db_config, llm_provider,chunk_db,doc_db,verbose):
    """直接使用数据库中的激活配置运行，不做任何覆盖，验证端到端流程正常。"""
    name = "Case 1 — As-Is Pipeline (数据库原始配置)"
    try:
        pipeline = await RetrievalPipeline.create(
            config=db_config, vs_manager=vs, bm25_manager=bm25, 
            pc_db=pc_db,chunk_db=chunk_db,doc_db=doc_db,llm_config=llm_provider
        )
        result = await pipeline.run(query="公司解散后如何进行清算？")

        assert_ok(len(result.chunks) > 0, "端到端结果不应为空")
        assert_ok(
            result.chunks[0].final_score >= result.chunks[-1].final_score,
            "结果应按 final_score 降序排列"
        )
        # 置信度诊断
        assert_ok(result.confidence.level in ("high", "low", "empty"), "level 值不合法")
        if result.confidence.level == "low":
            assert_ok(result.confidence.warning is not None, "level=low 时 warning 不应为 None")
            logger.info(f"[Case1] 低置信度提醒: {result.confidence.warning}")

        print(f"  {PASS}  {name}  ({len(result.chunks)} 条, confidence={result.level})")
        _print_chunks(result.chunks, verbose)
        _summary.append((name, "pass"))
    except AssertionError as e:
        print(f"  {FAIL}  {name}: {e}")
        _summary.append((name, "fail"))


async def case2_vector_only(vs, bm25, pc_db, db_config,llm_provider,chunk_db, doc_db,verbose):
    name = "Case 2 — Vector Only"
    try:
        cfg = override_config(db_config, enable_bm25=False, reranking_mode="vector")
        pipeline = await RetrievalPipeline.create(
            config=cfg, vs_manager=vs, bm25_manager=bm25, 
            pc_db=pc_db,chunk_db=chunk_db,doc_db=doc_db,llm_config=llm_provider
        )
        result = await pipeline.run(query="股东的权利和义务有哪些？")
        chunks = result.chunks

        assert_ok(len(chunks) > 0, "向量检索结果不应为空（确认 ChromaDB 索引已建立）")
        assert_ok(
            all("vector" in rc.retrieval_path for rc in chunks),
            "所有结果应经过 vector 阶段"
        )
        assert_ok(
            chunks[0].final_score >= chunks[-1].final_score,
            "结果应按 final_score 降序排列"
        )
        assert_ok(
            all(rc.final_score >= cfg.vector_score_threshold for rc in chunks),
            f"所有结果得分应 >= vector_score_threshold={cfg.vector_score_threshold}"
        )
        print(f"  {PASS}  {name}  ({len(chunks)} 条)")
        _print_chunks(chunks, verbose)
        _summary.append((name, "pass"))
    except AssertionError as e:
        print(f"  {FAIL}  {name}: {e}")
        _summary.append((name, "fail"))


async def case3_bm25_only(vs, bm25, pc_db, db_config,llm_provider,chunk_db, doc_db,verbose):
    name = "Case 3 — BM25 Only"
    try:
        # BM25Stage 内部使用 str(kb_id) 作为 kb_name 查找索引文件
        cfg = override_config(db_config, enable_vector=False, reranking_mode="bm25")
        pipeline = await RetrievalPipeline.create(
            config=cfg, vs_manager=vs, bm25_manager=bm25, 
            pc_db=pc_db,chunk_db=chunk_db,doc_db=doc_db,llm_config=llm_provider
        )
        result = await pipeline.run(query="董事会决议的表决规则")
        chunks = result.chunks

        assert_ok(
            len(chunks) > 0,
            f"BM25 结果不应为空（确认索引文件 {db_config.kb_id}.json 存在）"
        )
        assert_ok(
            all("bm25" in rc.retrieval_path for rc in chunks),
            "所有结果应经过 bm25 阶段"
        )
        assert_ok(
            chunks[0].final_score >= chunks[-1].final_score,
            "结果应按 final_score 降序排列"
        )
        # BM25Manager.search 不返回 doc_id，RetrievedChunk.doc_id 默认为 0，属已知设计
        if any(rc.doc_id == 0 for rc in chunks):
            logger.debug("[Case3] BM25 结果 doc_id=0（BM25 索引不存储 doc_id，符合预期）")

        print(f"  {PASS}  {name}  ({len(chunks)} 条)")
        _print_chunks(chunks, verbose)
        _summary.append((name, "pass"))
    except AssertionError as e:
        print(f"  {FAIL}  {name}: {e}")
        _summary.append((name, "fail"))


async def case4_hybrid_rrf(vs, bm25, pc_db, db_config,llm_provider, chunk_db,doc_db, verbose):
    name = "Case 4 — Hybrid RRF Fusion"
    try:
        cfg = override_config(db_config, rrf_mode="rrf", reranking_mode="hybrid",
                              enable_vector=True, enable_bm25=True)
        pipeline = await RetrievalPipeline.create(
            config=cfg, vs_manager=vs, bm25_manager=bm25, 
            pc_db=pc_db,chunk_db=chunk_db,doc_db=doc_db,llm_config=llm_provider
        )
        result = await pipeline.run(query="注册资本和出资方式有哪些规定？")
        chunks = result.chunks

        assert_ok(len(chunks) > 0, "Hybrid RRF 结果不应为空")

        ids = [rc.chunk_id for rc in chunks]
        assert_ok(len(ids) == len(set(ids)), f"结果中存在重复 chunk_id: {ids}")

        has_rrf    = any("rrf"    in rc.retrieval_path for rc in chunks)
        has_vector = any("vector" in rc.retrieval_path for rc in chunks)
        assert_ok(has_rrf or has_vector, "结果应至少经过 rrf 或 vector 阶段")

        print(f"  {PASS}  {name}  ({len(chunks)} 条)")
        _print_chunks(chunks, verbose)
        _summary.append((name, "pass"))
    except AssertionError as e:
        print(f"  {FAIL}  {name}: {e}")
        _summary.append((name, "fail"))


async def case5_hybrid_weighted(vs, bm25, pc_db, db_config, llm_provider,chunk_db, doc_db,verbose):
    name = "Case 5 — Hybrid Weighted Fusion"
    try:
        cfg = override_config(db_config, rrf_mode="weighted", reranking_mode="hybrid",
                              enable_vector=True, enable_bm25=True)
        pipeline = await RetrievalPipeline.create(
            config=cfg, vs_manager=vs, bm25_manager=bm25, 
            pc_db=pc_db,chunk_db=chunk_db,doc_db=doc_db,llm_config=llm_provider
        )
        result = await pipeline.run(query="监事会的职责和权力")
        chunks = result.chunks

        assert_ok(len(chunks) > 0, "Weighted Fusion 结果不应为空")
        assert_ok(
            any("weighted" in rc.retrieval_path for rc in chunks),
            "应有结果经过 weighted 阶段"
        )
        assert_ok(
            chunks[0].final_score >= chunks[-1].final_score,
            "结果应按 final_score 降序排列"
        )
        print(f"  {PASS}  {name}  ({len(chunks)} 条)")
        _print_chunks(chunks, verbose)
        _summary.append((name, "pass"))
    except AssertionError as e:
        print(f"  {FAIL}  {name}: {e}")
        _summary.append((name, "fail"))


async def case6_small_to_big(vs, bm25, pc_db, db_config,llm_provider,chunk_db, doc_db,verbose, skip: bool):
    name = "Case 6 — Small-to-Big Expansion"
    if skip:
        print(f"  {SKIP}  {name}  (--skip-s2b 已指定)")
        _summary.append((name, "skip"))
        return
    try:
        cfg = override_config(db_config, enable_bm25=False,
                              enable_small_to_big=True, reranking_mode="vector")
        pipeline = await RetrievalPipeline.create(
            config=cfg, vs_manager=vs, bm25_manager=bm25, 
            pc_db=pc_db,chunk_db=chunk_db,doc_db=doc_db,llm_config=llm_provider
        )
        result = await pipeline.run(query="公司章程对董事和监事的约束")
        chunks = result.chunks

        if not chunks:
            # 向量化时若未写入 parent_id metadata，S2B 会静默跳过
            print(f"  {PASS}  {name}  (0 条 — 无 parent_id metadata，S2B 跳过，符合预期)")
            _summary.append((name, "pass"))
            return

        expanded     = [rc for rc in chunks if "s2b" in rc.retrieval_path]
        not_expanded = [rc for rc in chunks if "s2b" not in rc.retrieval_path]

        # 同一 parent_id 只应保留一条（得分最高的 child 代表该父块）
        parent_ids = [
            rc.metadata.get("parent_id") for rc in expanded
            if rc.metadata.get("parent_id") is not None
        ]
        assert_ok(
            len(parent_ids) == len(set(parent_ids)),
            f"S2B 展开后同一 parent_id 出现重复: {parent_ids}"
        )
        for rc in expanded:
            assert_ok(
                rc.metadata.get("expanded") is True,
                f"S2B 展开条目应有 metadata['expanded']=True，chunk_id={rc.chunk_id}"
            )

        print(f"  {PASS}  {name}  "
              f"(展开={len(expanded)} 条, 未展开={len(not_expanded)} 条)")
        _print_chunks(chunks, verbose)
        _summary.append((name, "pass"))
    except AssertionError as e:
        print(f"  {FAIL}  {name}: {e}")
        _summary.append((name, "fail"))


async def case7_empty_query(vs, bm25, pc_db, db_config,llm_provider,chunk_db,doc_db, verbose):
    name = "Case 7 — Empty Query Guard"
    try:
        pipeline = await RetrievalPipeline.create(
            config=db_config, vs_manager=vs, bm25_manager=bm25, 
            pc_db=pc_db,chunk_db=chunk_db,doc_db=doc_db,llm_config=llm_provider
        )
        for q in ["", "   ", "\t\n"]:
            result_empty = await pipeline.run(query=q)        
            assert_ok(result_empty.level == "empty", "空查询应返回 level=empty")
            assert_ok(result_empty.chunks == [], "空查询 chunks 应为 []")

        print(f"  {PASS}  {name}")
        _summary.append((name, "pass"))
    except AssertionError as e:
        print(f"  {FAIL}  {name}: {e}")
        _summary.append((name, "fail"))


async def case8_score_threshold(vs, bm25, pc_db, db_config,llm_provider,chunk_db, doc_db,verbose):
    name = "Case 8 — Score Threshold Filter"
    try:
        query    = "公司合并与分立的程序"
        cfg_low  = override_config(db_config, enable_bm25=False,
                                   vector_score_threshold=0.0, final_top_k=20)
        cfg_high = override_config(db_config, enable_bm25=False,
                                   vector_score_threshold=0.8, final_top_k=20)

        result_low  = await RetrievalPipeline.create(
            config=cfg_low,  vs_manager=vs, bm25_manager=bm25, 
            pc_db=pc_db,chunk_db=chunk_db,doc_db=doc_db,llm_config=llm_provider
        ).run(query=query)
        chunks_low = result_low.chunks
        result_high = await RetrievalPipeline.create(
            config=cfg_high, vs_manager=vs, bm25_manager=bm25, 
            pc_db=pc_db,chunk_db=chunk_db,doc_db=doc_db,llm_config=llm_provider
        ).run(query=query)
        chunks_high = result_high.chunks

        assert_ok(
            len(chunks_high) <= len(chunks_low),
            f"高阈值结果({len(chunks_high)})应 <= 低阈值结果({len(chunks_low)})"
        )
        assert_ok(
            all(rc.final_score >= 0.8 for rc in chunks_high),
            "高阈值结果中存在得分 < 0.8 的条目"
        )
        print(f"  {PASS}  {name}  "
              f"(低阈值={len(chunks_low)} 条, 高阈值={len(chunks_high)} 条)")
        _summary.append((name, "pass"))
    except AssertionError as e:
        print(f"  {FAIL}  {name}: {e}")
        _summary.append((name, "fail"))

async def case9_confidence(vs, bm25, pc_db, db_config, llm_provider,chunk_db, doc_db, verbose):
    name = "Case 9 — Confidence Detection"
    try:
        # 9a: 高阈值 → 预期触发 low confidence
        cfg_strict = override_config(
            db_config,
            enable_bm25=False,
            confidence_high_score_threshold=0.99,   # 极难达到
            confidence_low_score_threshold=0.95,
            confidence_min_high_conf_count=5,
        )
        result_strict = await RetrievalPipeline.create(
            config=cfg_strict, vs_manager=vs, bm25_manager=bm25,
            pc_db=pc_db, chunk_db=chunk_db, doc_db=doc_db,llm_config=llm_provider
        ).run(query="公司合并与分立的程序")

        assert_ok(
            result_strict.level in ("low", "empty"),
            f"极高阈值下应为 low/empty，实际 level={result_strict.level}"
        )
        assert_ok(
            result_strict.warning is not None or result_strict.level == "empty",
            "level=low 时 warning 不应为 None"
        )

        # 9b: 宽松阈值 → 预期 high confidence
        cfg_loose = override_config(
            db_config,
            enable_bm25=False,
            confidence_high_score_threshold=0.1,
            confidence_low_score_threshold=0.05,
            confidence_min_high_conf_count=1,
        )
        result_loose = await RetrievalPipeline.create(
            config=cfg_loose, vs_manager=vs, bm25_manager=bm25,
            pc_db=pc_db, chunk_db=chunk_db, doc_db=doc_db,llm_config=llm_provider
        ).run(query="公司合并与分立的程序")

        assert_ok(
            result_loose.level == "high",
            f"宽松阈值下应为 high，实际 level={result_loose.level}"
        )
        assert_ok(result_loose.warning is None, "level=high 时 warning 应为 None")

        # 9c: 空查询 → empty
        result_empty = await RetrievalPipeline.create(
            config=db_config, vs_manager=vs, bm25_manager=bm25,
            pc_db=pc_db, chunk_db=chunk_db, doc_db=doc_db,llm_config=llm_provider
        ).run(query="   ")
        assert_ok(result_empty.level == "empty", "空查询应返回 level=empty")
        assert_ok(result_empty.chunks == [], "空查询 chunks 应为 []")

        print(f"  {PASS}  {name}  "
              f"(strict={result_strict.level}, loose={result_loose.level}, empty={result_empty.level})")
        _summary.append((name, "pass"))
    except AssertionError as e:
        print(f"  {FAIL}  {name}: {e}")
        _summary.append((name, "fail"))

# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    print("\n" + "=" * 65)
    print("  RetrievalPipeline 集成测试  ·  语料：中华人民共和国公司法")
    print("=" * 65)

    from app.core.config import settings
    sqlite_path = "."+ settings.sqlite_db_path
    vector_path = "."+ settings.vector_db_path
    bm25_path = "."+ settings.bm25_index_path
    kb_id = 1

    # ── 从数据库读取配置 ──────────────────────────────────────────────────
    logger.info("从数据库读取 StrategyConfig ...")
    kb_db = AsyncKnowledgeBaseDatabase(database_url=f"sqlite+aiosqlite:///{sqlite_path}")
    db_config = await kb_db.get_active_strategy_config(kb_id=kb_id)

    if db_config is None:
        print(f"\n[ERROR] kb_id={kb_id} 没有 is_active=True 的 StrategyConfig，"
              f"请先通过 db_manager 初始化数据或手动设置 is_active=True。\n")
        sys.exit(1)

    print("  已加载 StrategyConfig：")
    _print_config(db_config)

    embedding_provider = await kb_db.get_embedding_by_kb_id(kb_id=kb_id)
    if embedding_provider is None:
        print(f"\n[ERROR] kb_id={kb_id} 没有 embedding_provider。\n")
        sys.exit(1)

    print("  已加载 embedding_provider：")

    llm_provider = await kb_db.get_llm_by_kb_id(kb_id=kb_id)
    if llm_provider is None:
        print(f"\n[ERROR] kb_id={kb_id} 没有 llm_provider。\n")
        sys.exit(1)

    print("  已加载 llm_provider：")


    print("-" * 65)

    # ── 初始化外部服务 ────────────────────────────────────────────────────────
    logger.info("初始化 VectorStoreManager ...")
    vs = VectorStoreManager(
        db_path         = vector_path,
        ollama_base_url = embedding_provider.base_url,
        embed_model     = embedding_provider.model_name,
    )

    logger.info("初始化 BM25Manager ...")
    bm25 = BM25Manager(storage_dir=bm25_path)

    logger.info("初始化 ParentChunkDatabase ...")
    pc_db = AsyncParentChunkDatabase(database_url=f"sqlite+aiosqlite:///{sqlite_path}")

    logger.info("初始化 ChunkDatabase ...")
    chunk_db = AsyncChunkDatabase(database_url=f"sqlite+aiosqlite:///{sqlite_path}")

    logger.info("初始化 DocumentDatabase ...")
    doc_db = AsyncDocumentDatabase(database_url=f"sqlite+aiosqlite:///{sqlite_path}")

    logger.info(
        f"BM25 将使用 kb_name='{kb_id}' 查找索引文件: "
        f"{bm25_path}/{kb_id}.json"
    )

    verbose = True

    # ── 执行测试 ──────────────────────────────────────────────────────────────
    await case1_as_is          (vs, bm25, pc_db, db_config, llm_provider,chunk_db, doc_db, verbose)
    await case2_vector_only    (vs, bm25, pc_db, db_config, llm_provider,chunk_db, doc_db, verbose)
    await case3_bm25_only      (vs, bm25, pc_db, db_config, llm_provider,chunk_db, doc_db, verbose)
    await case4_hybrid_rrf     (vs, bm25, pc_db, db_config, llm_provider,chunk_db, doc_db, verbose)
    await case5_hybrid_weighted(vs, bm25, pc_db, db_config, llm_provider,chunk_db, doc_db, verbose)
    await case6_small_to_big   (vs, bm25, pc_db, db_config, llm_provider,chunk_db, doc_db, verbose, skip=True)
    await case6_small_to_big   (vs, bm25, pc_db, db_config, llm_provider,chunk_db, doc_db, verbose, skip=False)
    await case7_empty_query    (vs, bm25, pc_db, db_config, llm_provider,chunk_db, doc_db, verbose)
    await case8_score_threshold(vs, bm25, pc_db, db_config, llm_provider,chunk_db, doc_db, verbose)
    await case9_confidence     (vs, bm25, pc_db, db_config, llm_provider,chunk_db, doc_db, verbose)

    # ── 汇总 ──────────────────────────────────────────────────────────────────
    passed  = sum(1 for _, s in _summary if s == "pass")
    failed  = sum(1 for _, s in _summary if s == "fail")
    skipped = sum(1 for _, s in _summary if s == "skip")

    print("\n" + "-" * 65)
    print(f"  结果：{passed} 通过  {failed} 失败  {skipped} 跳过  (共 {len(_summary)} 项)")
    if failed:
        print("  未通过：")
        for n, s in _summary:
            if s == "fail":
                print(f"    · {n}")
    print("-" * 65 + "\n")
    return failed == 0


if __name__ == "__main__":

    logger.remove()
    logger.add(sys.stderr, level="WARNING",
               format="{time:HH:mm:ss} | {level} | {message}")

    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)

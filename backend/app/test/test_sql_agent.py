#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-30
# @description: test case

import sys, os
current_file_path = os.path.abspath(__file__)
current_folder = os.path.dirname(current_file_path)
root_path = os.path.dirname(current_folder)
if root_path not in sys.path:
    sys.path.insert(0, root_path)

from app.services.sql_agent.sql_tools import SQLTools
from app.services.sql_agent.agent import SQLAgent
from app.infra.db.duckdb_manager import DuckDBManager
from app.services.sql_agent.manager import DBManager
from app.runtime.llm.client import LLMClient
from app.runtime.llm.agent_client import AgentLLM

SCHEMA = "liu"

# =========================
# 初始化 LLM
# =========================
client = LLMClient(
    base_url="http://localhost:11434/v1",  # Ollama
    api_key="none"
)
llm = AgentLLM(client, model="qwen3:4b")

# =========================
# 1. 初始化数据库
# =========================
duckdb_manager = DuckDBManager(db_path="test.db")
db_manager = DBManager(duckdb_manager=duckdb_manager)

# =========================
# 2. 导入 CSV
# =========================
table_name = db_manager.import_csv(
    file_path="./data/test_doc/orders.csv",
    schema_name=SCHEMA,
    primary_key="order_id"
)

# =========================
# 3. 初始化工具（新增 schema_name 参数）
# =========================
tools = SQLTools(duckdb_manager=duckdb_manager, schema_name=SCHEMA)

# =========================
# 4. 初始化 Agent
# =========================
agent = SQLAgent(llm=llm, tools=tools, schema_name=SCHEMA)

# =========================
# 5. 直接调用工具测试
# =========================
print("\n===== 测试：直接工具 - get_schema =====")
print(tools.get_schema("orders", schema_name=SCHEMA))

print("\n===== 测试：直接工具 - sample_data =====")
print(tools.sample_data("orders", schema_name=SCHEMA))

print("\n===== 测试：直接工具 - sample_data =====")
print(tools.execute_sql("select count(*) from liu.orders"))

# =========================
# 6. 测试问题1：总数
# =========================
print("\n===== 测试1：订单数量 =====")
result = agent.run("orders 表有多少条数据？")
print(result)

# =========================
# 7. 测试问题2：收入
# =========================
print("\n===== 测试2：总收入 =====")
result = agent.run("已支付订单的总收入是多少？")
print(result)

# =========================
# 8. 测试run_python：简单汇总
# =========================
print("\n===== 测试5：简单数据分析 =====")
result = agent.run("请按国家分析订单的总金额和支付成功率。")
print(result)
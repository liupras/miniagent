#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-04-30
# @description: test case

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
# 5. 测试run_python
# =========================
print("\n===== 测试1：直接工具 - run_python =====")
code = """
import pandas as pd

df = conn.execute(f"SELECT * FROM {schema_name}.orders").fetchdf()
print(f"行数: {len(df)}")
print(f"列名: {list(df.columns)}")
df.describe()
"""
result = tools.run_python(code)
print(result)

print("\n===== 测试2：直接工具 - 绘制图片 =====")
code = """
import pandas as pd
import matplotlib.pyplot as plt
import io
import base64

df = conn.execute(f'SELECT country, SUM(amount) as total FROM {schema_name}.orders GROUP BY country').fetchdf()

plt.figure(figsize=(8, 4))
plt.bar(df['country'], df['total'])
plt.title('Total Sales by Country')

buf = io.BytesIO()
plt.savefig(buf, format='png')
img_str = base64.b64encode(buf.getvalue()).decode()

print('Chart generated successfully.')
f'data:image/png;base64,{img_str}'
"""
result = tools.run_python(code)
print(result)

print("\n===== 测试1：绘制饼图 =====")
result = agent.run("请用饼图绘制各个国家已支付订单的总收入占比。")
print(result)

print("\n===== 测试1：复杂数据分析 =====")
result = agent.run("请使用 IQR (四分位距) 方法检测 orders 表中 amount 字段的异常值。")
print(result)

# =========================
# 6. run_python 超时测试
# =========================
print("\n===== 测试73run_python 超时 =====")
result = tools.run_python("while True: pass")
print(result)  # 预期: error 含 "exceeded ... time limit"

# =========================
# 7. run_python 安全拦截测试
# =========================
print("\n===== 测试4：run_python 安全拦截 =====")
result = tools.run_python("import os; os.system('whoami')")
print(result)  # 预期: error 含 "not allowed"



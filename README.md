# MiniAgent - 轻量级智能体平台

为个人或小团队提供轻便好用、易于部署和维护的智能体/Agent平台。

**Simple Architecture + Explicit Code（简单架构 + 显式代码）**
Make the simple things simple, and the complex things possible.

## 特性

- 🤖 多智能体支持
- 📚 多知识库管理
- 🔧 可扩展的工具系统
- 🌐 支持多种LLM（Ollama、OpenAI等）
- 🗄️ 向量化知识库（ChromaDB）
- 🌍 中英文双语支持

## 技术栈

- 前端: pureAdmin
- 后端: FastAPI + Python 3.12+
- 向量数据库: ChromaDB
- 结构化数据: SQLite、DuckDB
- LLM适配: 自研轻量级适配层（预留MCP兼容）

2. 前后端增加密码复杂度限制
	- 至少 8 位
	- 至少一个大写
	- 至少一个小写
	- 至少一个数字

3. 登录失败锁定
连续失败5次，锁定10分钟，管理员可以后台解除锁定。

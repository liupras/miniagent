# MiniAgent - 轻量级智能体平台

为个人或小团队提供轻便好用、易于部署和维护的智能体/Agent平台。

## 特性

- 🤖 多智能体支持
- 📚 多知识库管理
- 🔧 可扩展的工具系统
- 🌐 支持多种LLM（Ollama、OpenAI等）
- 🗄️ 向量化知识库（ChromaDB）
- 🌍 中英文双语支持

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <your-repo>
cd miniagent

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r backend/requirements.txt
```

### 2. 配置

```bash
# 复制环境变量模板
cp backend/.env.example backend/.env

# 编辑 .env 文件，填入你的配置
```

### 3. 运行

```bash
# 初始化数据库
python backend/app/init_db.py

# 启动服务
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000/docs 查看API文档

## 项目结构

```
miniagent/
├── backend/                # 后端代码
│   ├── app/
│   │   ├── main.py        # FastAPI入口
│   │   ├── config.py      # 配置管理
│   │   ├── models/        # 数据模型
│   │   ├── core/          # 核心功能（Agent引擎、LLM适配等）
│   │   ├── api/           # API路由
│   │   └── utils/         # 工具函数
│   └── requirements.txt
├── data/                   # 数据目录
│   ├── chroma_data/       # 向量数据库
│   └── sqlite/            # SQLite数据库
└── docs/                   # 文档
```

## 开发路线图

- [x] MVP阶段: 单智能体 + 单知识库 + 基础对话
- [ ] 第二阶段: 多知识库支持 + 工具调用框架
- [ ] 第三阶段: 多智能体协作 + 高级检索策略
- [ ] 第四阶段: 监控面板 + 成本优化
- [ ] 第五阶段: 前端UI + OpenAI API兼容

## 技术栈

- 后端: FastAPI + Python 3.9+
- 向量数据库: ChromaDB
- 结构化数据: SQLite
- LLM适配: 自研轻量级适配层（预留MCP兼容）

## 许可证

MIT License

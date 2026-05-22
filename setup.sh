#!/bin/bash

# MiniAgent 快速启动脚本

set -e

echo "=================================="
echo "  MiniAgent 快速启动工具"
echo "=================================="

# 检查Python版本
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到Python3，请先安装Python 3.9或更高版本"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✅ Python版本: $PYTHON_VERSION"

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
    echo "✅ 虚拟环境创建成功"
else
    echo "✅ 虚拟环境已存在"
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source venv/bin/activate

# 安装依赖
echo "📥 安装依赖包..."
pip install --upgrade pip
pip install -r backend/requirements.txt

# 检查.env文件
if [ ! -f "backend/.env" ]; then
    echo "⚠️ 未找到.env文件，正在从模板创建..."
    cp backend/.env.example backend/.env
    echo "✅ .env文件已创建，请编辑backend/.env文件配置你的API密钥"
    echo ""
    echo "重要配置项："
    echo "  - OPENAI_API_KEY: 如果使用OpenAI，请填入你的API密钥"
    echo "  - OLLAMA_API_BASE: 如果使用Ollama，确保地址正确"
    echo ""
    read -p "是否现在编辑.env文件？(y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ${EDITOR:-nano} backend/.env
    fi
fi

# 初始化数据库
echo "🗄️ 初始化数据库..."
cd backend
python app/init_db.py init
cd ..

echo ""
echo "=================================="
echo "✅ 环境准备完成！"
echo "=================================="
echo ""
echo "🚀 启动服务："
echo "   cd backend"
echo "   python -m uvicorn app.main:app --reload"
echo ""
echo "或者使用："
echo "   cd backend && python app/main.py"
echo ""
echo "📚 访问API文档: http://localhost:8000/docs"
echo ""

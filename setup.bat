@echo off
REM MiniAgent 快速启动脚本 (Windows)

echo ==================================
echo   MiniAgent 快速启动工具
echo ==================================
echo.

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 未找到Python，请先安装Python 3.9或更高版本
    pause
    exit /b 1
)

echo ✅ Python已安装

REM 创建虚拟环境
if not exist "venv" (
    echo 📦 创建虚拟环境...
    python -m venv venv
    echo ✅ 虚拟环境创建成功
) else (
    echo ✅ 虚拟环境已存在
)

REM 激活虚拟环境
echo 🔧 激活虚拟环境...
call venv\Scripts\activate.bat

REM 安装依赖
echo 📥 安装依赖包...
python -m pip install --upgrade pip
pip install -r backend\requirements.txt

REM 检查.env文件
if not exist "backend\.env" (
    echo ⚠️ 未找到.env文件，正在从模板创建...
    copy backend\.env.example backend\.env
    echo ✅ .env文件已创建
    echo.
    echo 请编辑 backend\.env 文件配置你的API密钥
    echo.
    echo 重要配置项：
    echo   - OPENAI_API_KEY: 如果使用OpenAI，请填入你的API密钥
    echo   - OLLAMA_API_BASE: 如果使用Ollama，确保地址正确
    echo.
    pause
    notepad backend\.env
)

REM 初始化数据库
echo 🗄️ 初始化数据库...
cd backend
python app\init_db.py init
cd ..

echo.
echo ==================================
echo ✅ 环境准备完成！
echo ==================================
echo.
echo 🚀 启动服务：
echo    cd backend
echo    python -m uvicorn app.main:app --reload
echo.
echo 或者使用：
echo    cd backend ^&^& python app\main.py
echo.
echo 📚 访问API文档: http://localhost:8000/docs
echo.
pause

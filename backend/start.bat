@echo off
cd /d "%~dp0"

:: 激活虚拟环境
call .venv\Scripts\activate.bat

:: 启动 FastAPI
python -m uvicorn app.main:app --reload --port 10088

pause

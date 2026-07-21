@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"
set "ROOT_DIR=%~dp0"
set "VENV_DIR=%~dp0backend\.venv"
set "VENV_PYTHON=%~dp0backend\.venv\Scripts\python.exe"

title MiniAgent One-click Launcher
echo ==========================================
echo   MiniAgent Windows One-click Launcher
echo ==========================================
echo.

REM Locate Python 3.12+.
where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto :python_found
)

where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
    goto :python_found
)

echo [ERROR] Python was not found. Install Python 3.12 or later.
goto :failed

:python_found
%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] MiniAgent requires Python 3.12 or later.
    goto :failed
)
echo [OK] Python is available.

REM Check Node.js version required by both frontends.
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js was not found. Install Node.js 20.19+ or 22.13+.
    goto :failed
)
node -e "const [a,b]=process.versions.node.split('.').map(Number);process.exit(a===20?b>=19?0:1:a===22?b>=13?0:1:a>22?0:1)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] MiniAgent requires Node.js 20.19+ or 22.13+.
    goto :failed
)
echo [OK] Node.js is available.

REM Prefer an installed pnpm; otherwise use the Corepack bundled with Node.js.
where pnpm >nul 2>&1
if not errorlevel 1 (
    set "PNPM_CMD=pnpm"
    goto :pnpm_found
)

where corepack >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pnpm was not found. Run: npm install -g pnpm
    goto :failed
)
set "PNPM_CMD=corepack pnpm"

:pnpm_found
call %PNPM_CMD% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pnpm could not be started. Check your Node.js/Corepack installation.
    goto :failed
)
echo [OK] pnpm is available.
echo.

REM Create and update the backend virtual environment.
if not exist "%VENV_PYTHON%" (
    echo [1/5] Creating Python virtual environment...
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 goto :failed
) else (
    echo [1/5] Python virtual environment already exists.
)

echo [2/5] Installing backend dependencies...
"%VENV_PYTHON%" -m pip install -r "%ROOT_DIR%backend\requirements.txt"
if errorlevel 1 goto :failed

REM Create the local configuration on first launch.
if not exist "%ROOT_DIR%backend\.env" (
    echo [INFO] Creating backend\.env from backend\.env.example...
    copy /Y "%ROOT_DIR%backend\.env.example" "%ROOT_DIR%backend\.env" >nul
    if errorlevel 1 goto :failed
)

echo [3/5] Initializing the database...
pushd "%ROOT_DIR%backend"
"%VENV_PYTHON%" -m app.infra.db.initializer init
if errorlevel 1 (
    popd
    goto :failed
)
popd

echo [4/5] Installing Management dependencies...
pushd "%ROOT_DIR%management"
call %PNPM_CMD% install --frozen-lockfile
if errorlevel 1 (
    popd
    goto :failed
)
popd

echo [5/5] Installing Workplace dependencies...
pushd "%ROOT_DIR%workplace"
call %PNPM_CMD% install --frozen-lockfile
if errorlevel 1 (
    popd
    goto :failed
)
popd

echo.
echo Starting Backend, Management, and Workplace...
start "MiniAgent Backend" cmd /k "cd /d ""%ROOT_DIR%backend"" && ""%VENV_PYTHON%"" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 10088"
start "MiniAgent Management" cmd /k "cd /d ""%ROOT_DIR%management"" && call %PNPM_CMD% dev --host 0.0.0.0 --port 8848"
start "MiniAgent Workplace" cmd /k "cd /d ""%ROOT_DIR%workplace"" && call %PNPM_CMD% dev --host 0.0.0.0 --port 5173"

echo.
echo ==========================================
echo   MiniAgent has been started
echo ==========================================
echo   Backend API: http://localhost:10088
echo   API docs:    http://localhost:10088/docs
echo   Management:  http://localhost:8848
echo   Workplace:   http://localhost:5173
echo.
echo Close the three service windows to stop MiniAgent.
echo The first launch may take several minutes to install dependencies.
pause
exit /b 0

:failed
echo.
echo [FAILED] Setup or startup preparation did not complete.
echo Review the error above, fix it, and run setup.bat again.
pause
exit /b 1

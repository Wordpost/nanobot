@echo off
REM =========================================================
REM Nanobot Forensic Viewer - Launcher (Windows)
REM Config is loaded from .env file or auto-detected.
REM =========================================================
pushd "%~dp0"

REM Activate venv
if not exist "venv\Scripts\activate.bat" (
    echo [Error] Virtual environment not found. Run setup.bat first.
    popd
    pause
    exit /b 1
)

if exist "frontend" (
    where npm >nul 2>&1
    if %errorlevel% equ 0 (
        echo [Info] Checking frontend dependencies and building Static SPA...
        pushd frontend
        if not exist "node_modules" call npm install
        call npm run build
        popd
    )
)

call venv\Scripts\activate.bat
python -m src.app
popd
pause

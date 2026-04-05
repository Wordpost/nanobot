@echo off
REM =========================================================
REM Nanobot Forensic Viewer - DEV Mode Launcher (Windows)
REM Starts BOTH FastAPI backend and Vite HMR frontend in separate windows.
REM =========================================================
pushd "%~dp0"

REM Check venv
if not exist "venv\Scripts\activate.bat" (
    echo [Error] Virtual environment not found. Run setup.bat first.
    popd
    pause
    exit /b 1
)

echo [Info] Starting FastAPI Backend (Port 2003)...
start "Vivir Backend" cmd /k "call venv\Scripts\activate.bat && title Vivir Backend && python -m src.app"

echo [Info] Starting Vite Dev Server (HMR, Port 5173)...
if exist "frontend" (
    pushd frontend
    if not exist "node_modules" call npm install
    start "Vivir Frontend (Vite)" cmd /k "title Vivir Frontend && npm run dev"
    popd
) else (
    echo [Error] Frontend directory not found!
)

echo.
echo =========================================================
echo [Success] Development mode initiated!
echo 1. Backend window opened (FastAPI: 2003)
echo 2. Frontend window opened (Vite: 5173)
echo.
echo Please open http://localhost:5173 in your browser for development.
echo =========================================================
echo.
popd
pause

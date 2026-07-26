@echo off
setlocal

echo ========================================
echo   JobApply - Starting Services
echo ========================================
echo.

:: Check if Node.js is installed
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Node.js is not installed. Please install Node.js first.
    pause
    exit /b 1
)

:: Check if Python is installed
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed. Please install Python first.
    pause
    exit /b 1
)

echo [1/3] Starting Backend Server...
start "JobApply Backend" cmd /c "cd /d D:\installed_softwares\naukri-cdp-apply\jobapply\backend && npm run dev"

timeout /t 3 /nobreak >nul

echo [2/3] Starting Frontend...
start "JobApply Frontend" cmd /c "cd /d D:\installed_softwares\naukri-cdp-apply\jobapply\frontend && npm run dev"

timeout /t 3 /nobreak >nul

echo [3/3] Starting Bot Orchestrator...
start "JobApply Bots" cmd /c "cd /d D:\installed_softwares\naukri-cdp-apply\jobapply\bots && if exist venv (venv\Scripts\activate.bat) else (python -m venv venv && venv\Scripts\activate.bat && pip install -r requirements.txt) && python main.py"

echo.
echo ========================================
echo   All services starting...
echo   Frontend: http://localhost:5173
echo   Backend:  http://localhost:3001
echo ========================================
echo.
echo Press any key to exit this window...
pause >nul

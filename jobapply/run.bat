@echo off
setlocal enabledelayedexpansion

title JobApply Auto-Start
color 0A

echo ==========================================
echo   JobApply - Automated Job Application
echo   Starting Services...
echo ==========================================
echo.

:: Check if running from correct directory
if not exist "backend\package.json" (
    echo [ERROR] Please run this script from the project root directory.
    echo Current directory: %CD%
    echo.
    echo Expected structure:
    echo   - backend\package.json
    echo   - frontend\package.json
    echo   - bots\requirements.txt
    pause
    exit /b 1
)

:: Check Node.js
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed or not in PATH.
    echo Please install Node.js from https://nodejs.org/
    pause
    exit /b 1
)

:: Check npm
where npm >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] npm is not installed.
    echo Please reinstall Node.js.
    pause
    exit /b 1
)

:: Check Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python from https://python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

:: Check Python version
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python command failed.
    pause
    exit /b 1
)

echo [OK] All prerequisites found.
echo.

:: Create logs directory
if not exist "logs" mkdir logs

:: ==========================================
:: Start Backend
:: ==========================================
echo [INFO] Starting Backend Server...
cd backend

if not exist "node_modules" (
    echo [INFO] Installing backend dependencies...
    call npm install
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install backend dependencies.
        cd ..
        pause
        exit /b 1
    )
)

if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] Creating .env from .env.example...
        copy .env.example .env >nul
    ) else (
        echo [WARNING] No .env or .env.example found. Creating default .env...
        echo PORT=3001> .env
        echo HOST=localhost>> .env
    )
)

:: Check if port 3001 is already in use
netstat -ano | findstr ":3001" >nul
if not errorlevel 1 (
    echo [WARNING] Port 3001 is already in use. Attempting to start anyway...
)

ver >nul
start "JobApply Backend" cmd /k "echo Starting backend... && npm run dev"
if !errorlevel! neq 0 (
    echo [ERROR] Failed to start backend server.
    cd ..
    pause
    exit /b 1
)
cd ..
echo [OK] Backend started in new window.
timeout /t 3 /nobreak >nul

:: ==========================================
:: Start Frontend
:: ==========================================
echo [INFO] Starting Frontend...
cd frontend

if not exist "node_modules" (
    echo [INFO] Installing frontend dependencies...
    call npm install
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install frontend dependencies.
        cd ..
        pause
        exit /b 1
    )
)

:: Check if port 5173 is already in use
netstat -ano | findstr ":5173" >nul
if not errorlevel 1 (
    echo [WARNING] Port 5173 is already in use. Attempting to start anyway...
)

ver >nul
start "JobApply Frontend" cmd /k "echo Starting frontend... && npm run dev"
if !errorlevel! neq 0 (
    echo [ERROR] Failed to start frontend.
    cd ..
    pause
    exit /b 1
)
cd ..
echo [OK] Frontend started in new window.
timeout /t 3 /nobreak >nul

:: ==========================================
:: Start Bots
:: ==========================================
echo [INFO] Starting Bot Orchestrator...
cd bots

:: Check requirements.txt
if not exist "requirements.txt" (
    if exist "..\requirements.txt" (
        copy "..\requirements.txt" "requirements.txt" >nul
    ) else (
        echo [ERROR] requirements.txt not found in bots directory.
        cd ..
        pause
        exit /b 1
    )
)

:: Create virtual environment if it doesn't exist
if not exist "venv" (
    echo [INFO] Creating Python virtual environment...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create virtual environment.
        echo Try running: python -m venv venv manually
        cd ..
        pause
        exit /b 1
    )
)

:: Activate virtual environment and install dependencies
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat
if !errorlevel! neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    cd ..
    pause
    exit /b 1
)

echo [INFO] Installing Python dependencies...
pip install -r requirements.txt --quiet
if !errorlevel! neq 0 (
    echo [WARNING] Some Python packages may have failed to install.
    echo Continuing anyway...
)

:: Check for Chrome/Chromium
where chrome >nul 2>nul
if !errorlevel! neq 0 (
    where chromium >nul 2>nul
    if !errorlevel! neq 0 (
        echo [WARNING] Google Chrome not found. Bots may fail.
        echo Please install Google Chrome.
    )
)

ver >nul
start "JobApply Bots" cmd /k "call venv\Scripts\activate.bat && echo Starting bot orchestrator... && python main.py --platform all"
if !errorlevel! neq 0 (
    echo [ERROR] Failed to start bot orchestrator.
    cd ..
    pause
    exit /b 1
)
cd ..
echo [OK] Bots started in new window.

:: ==========================================
:: Final Status
:: ==========================================
echo.
echo ==========================================
echo   All services started successfully!
echo ==========================================
echo.
echo   Backend:  http://localhost:3001
echo   Frontend: http://localhost:5173
echo   Bots:     Running in background
echo.
echo   Open your browser to: http://localhost:5173
echo.
echo   To stop services, close the three new windows.
echo ==========================================
echo.

:: Wait a moment then open browser
timeout /t 5 /nobreak >nul
start http://localhost:5173

exit /b 0

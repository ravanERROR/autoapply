

@echo off
title 🛸 Optimized Naukri Bot Launcher
color 0B
cd /d "%~dp0"

:menu
cls
echo ======================================================================
echo                     🛸 OPTIMIZED NAUKRI BOT LAUNCHER
echo ======================================================================
echo.
echo  [1] Standard Mode
echo      - Uses personal.json configuration
echo      - Applies filters and fills forms without AI assistance
echo.
echo  [2] Gemini AI Mode
echo      - Uses Gemini AI (gemini-2.5-flash) to answer form questions
echo      - Automatically handles unknown questions based on your profile
echo.
echo  [3] Exit
echo.
echo ======================================================================
set /p choice="Enter your choice (1-3): "

if "%choice%"=="1" goto standard
if "%choice%"=="2" goto ai
if "%choice%"=="3" goto exit
echo.
echo [ERROR] Invalid choice! Please select 1, 2, or 3.
pause
goto menu

:standard
cls
echo ======================================================================
echo           🛸 Starting Naukri Bot in Standard Mode...
echo ======================================================================
echo.
python naukri_bot.py
echo.
echo Bot session ended.
pause
goto menu

:ai
cls
echo ======================================================================
echo           🛸 Starting Naukri Bot in Gemini AI Mode...
echo ======================================================================
echo.
python naukri_bot.py ai
echo.
echo Bot session ended.
pause
goto menu

:exit
echo.
echo Goodbye!
timeout /t 3 >nul
exit /b

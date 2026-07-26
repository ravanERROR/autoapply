@echo off
setlocal

echo Starting JobApply services...

start "JobApply Backend" cmd /c "cd /d D:\installed_softwares\naukri-cdp-apply\jobapply\backend && npx tsx watch src/server.ts"
start "JobApply Frontend" cmd /c "cd /d D:\installed_softwares\naukri-cdp-apply\jobapply\frontend && npx vite --port 3000"

echo.
echo Backend:  http://localhost:5000
echo Frontend: http://localhost:3000
echo.
echo Close this window to stop both services.
echo.

timeout /t 3 >nul
echo Checking services...
curl -s http://localhost:5000/health >nul && echo [OK] Backend is running || echo [FAIL] Backend not reachable
curl -s http://localhost:3000 >nul && echo [OK] Frontend is running || echo [FAIL] Frontend not reachable

pause

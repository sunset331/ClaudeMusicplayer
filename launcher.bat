@echo off
title Claude Music · Liquid Glass
cd /d "%~dp0"

set PYTHON=C:\ProgramData\miniconda3\python.exe
set BACKEND_PORT=8765
set FRONTEND_PORT=5173

echo.
echo   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
echo   ░     Claude Music · Liquid Glass      ░
echo   ░     后端 :8765 | 前端 :5173          ░
echo   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
echo.

echo [1/3] Starting Python backend...
start "ClaudeMusic-Backend" /min cmd /c "cd /d %~dp0 && %PYTHON% backend\server.py"
echo        Backend starting on http://localhost:%BACKEND_PORT%

echo [2/3] Waiting for backend (may take 5-10s)...
:wait_backend
timeout /t 2 /nobreak >nul
curl -s http://localhost:%BACKEND_PORT%/api/status >nul 2>&1
if errorlevel 1 (
    echo        Still waiting...
    goto wait_backend
)
echo        Backend ready!

echo [3/3] Starting frontend dev server...
start "ClaudeMusic-Frontend" /min cmd /c "cd /d %~dp0desktop && npx vite --port %FRONTEND_PORT% --host"
echo        Frontend starting on http://localhost:%FRONTEND_PORT%
echo        (first launch may take 30-60s for Vite to warm up)

echo.
echo   ════════════════════════════════════════
echo     Opening browser in 5 seconds...
echo     Press any key here to STOP all
echo   ════════════════════════════════════════
echo.

timeout /t 5 /nobreak >nul
start "" http://localhost:%FRONTEND_PORT%

pause >nul

echo.
echo Shutting down...
taskkill /fi "WINDOWTITLE eq ClaudeMusic-Backend*" /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq ClaudeMusic-Frontend*" /f >nul 2>&1
echo Done.
timeout /t 1 >nul

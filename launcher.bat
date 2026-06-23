@echo off
title Claude Music · Liquid Glass
cd /d "%~dp0"

set PYTHON=F:\miniconda3\python.exe

REM Load .env file if it exists
if exist .env (
    for /f "usebackq tokens=* delims=" %%a in (.env) do set %%a
)

echo.
echo   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
echo   ░     Claude Music · Liquid Glass      ░
echo   ░     http://localhost:8765            ░
echo   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
echo.
echo Starting Claude Music server...
echo.
echo   Press any key to stop
echo.

start "" /B /MIN cmd /c "%PYTHON% backend\server.py"

pause >nul

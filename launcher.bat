@echo off
title Claude Music · Liquid Glass
cd /d "%~dp0"

set PYTHON=C:\ProgramData\miniconda3\python.exe

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

%PYTHON% backend\server.py

pause >nul

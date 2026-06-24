@echo off
title Claude Music
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "F:\projects\music-player"
start "" "F:\miniconda3\python.exe" "F:\projects\music-player\app.py"

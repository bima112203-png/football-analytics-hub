@echo off
title Football Analytics Hub
cd /d "%~dp0backend"
echo ========================================================
echo  Menjalankan Football Analytics Hub (http://localhost:8000)
echo ========================================================
echo.
start "" http://localhost:8000
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause

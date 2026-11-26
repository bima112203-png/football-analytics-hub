@echo off
title Update Data & Kirim ke Google Spreadsheet
cd /d "%~dp0backend"
echo ================================================================
echo  Sinkronisasi Web -> Simpan Offline -> Kirim ke Google Sheets
echo ================================================================
echo.
.venv\Scripts\python.exe -m scripts.push_to_gsheet
pause

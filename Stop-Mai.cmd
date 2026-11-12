@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -X utf8 launcher.py stop
if errorlevel 1 pause

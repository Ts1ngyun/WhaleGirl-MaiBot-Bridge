@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Missing bridge environment. See docs/INSTALL.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -X utf8 launcher.py start
if errorlevel 1 pause

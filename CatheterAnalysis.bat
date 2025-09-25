@echo off
cd /d "%~dp0"

REM Run BetterGUI.py with the virtual environment's Python
"%~dp0.venv\Scripts\python.exe" "%~dp0BetterGUI.py"

pause

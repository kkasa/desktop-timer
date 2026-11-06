@echo off
chcp 65001 > nul
cd /d "%~dp0"

if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" app.py %*
) else if exist "venv\Scripts\python.exe" (
    start "" "venv\Scripts\python.exe" app.py %*
) else (
    start "" pythonw app.py %*
)

if errorlevel 1 (
    echo [ERROR] Failed to start in background, running in console:
    python app.py %*
    pause
)

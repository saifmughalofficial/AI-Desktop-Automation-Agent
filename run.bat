@echo off
setlocal EnableExtensions
title AI Desktop Automation Agent
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] The virtual environment was not found.
    echo         Run setup.bat first ^(one time^), then run.bat again.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
python -c "import streamlit" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Dependencies are missing or broken. Run setup.bat again.
    pause
    exit /b 1
)

echo.
echo  AI Desktop Automation Agent is starting at http://localhost:8797
echo  Your browser opens automatically. Keep this window open; close it to stop the agent.
echo.
python -m app.main
if errorlevel 1 (
    echo.
    echo [ERROR] The agent stopped with an error. Read the messages above.
    echo         Common fixes: run setup.bat again, or close another copy using port 8797.
    pause
    exit /b 1
)
endlocal

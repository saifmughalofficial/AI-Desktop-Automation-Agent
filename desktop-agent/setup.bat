@echo off
setlocal EnableExtensions
title AI Desktop Automation Agent - Setup
cd /d "%~dp0"
echo.
echo  ==========================================================
echo    AI Desktop Automation Agent - one-time setup
echo    (no administrator rights needed, nothing outside this folder)
echo  ==========================================================
echo.

rem Prefer the "python" on PATH; fall back to the py launcher. Either must be 3.11+.
set "PY="
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=python"
if not defined PY (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    echo [ERROR] Python 3.11 or newer was not found.
    echo         Install it from https://www.python.org/downloads/
    echo         and tick "Add python.exe to PATH" during installation, then run setup.bat again.
    goto :fail
)
for /f "delims=" %%v in ('%PY% --version') do echo [OK] %%v

if not exist ".venv\Scripts\python.exe" (
    echo [..] Creating virtual environment in .venv
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Could not create the virtual environment.
        goto :fail
    )
) else (
    echo [OK] Virtual environment already exists
)

echo [..] Upgrading pip
".venv\Scripts\python.exe" -m pip install --upgrade pip --disable-pip-version-check -q
echo [..] Installing dependencies (this can take a few minutes the first time)
".venv\Scripts\python.exe" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo [ERROR] Dependency installation failed. Check your internet connection and the messages above.
    goto :fail
)

echo [..] Verifying installation
".venv\Scripts\python.exe" -c "import streamlit, pydantic, psutil, reportlab; import app.core.planner; print('[OK] Core modules import correctly')"
if errorlevel 1 (
    echo [ERROR] The agent's modules could not be imported.
    goto :fail
)
".venv\Scripts\python.exe" -c "import pywinauto" >nul 2>nul && echo [OK] pywinauto available - desktop UI automation enabled || echo [WARN] pywinauto not available - file automation still works

echo.
echo  Setup complete. Start the agent with run.bat
echo  Optional: install Ollama (https://ollama.com) and run "ollama pull llama3.2:3b" for local AI.
echo.
pause
exit /b 0

:fail
echo.
echo  Setup did not finish. Fix the problem above and run setup.bat again.
pause
exit /b 1

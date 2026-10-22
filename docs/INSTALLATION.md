# Installation

## Requirements
- Windows 10 or 11. File features also work on macOS and Linux, and in the hosted demo.
- Python 3.11 or newer from https://www.python.org/downloads/. Tick **Add python.exe to PATH** during installation.
- About 300 MB of disk space for the virtual environment. No administrator rights are needed.

## Setup
1. Double-click `setup.bat`. It:
   - checks that Python 3.11+ is installed and explains how to fix it if not
   - creates a private virtual environment in `.venv`
   - installs `requirements.txt` (Streamlit, Pydantic, psutil, ReportLab, pandas, pywinauto)
   - verifies the imports and reports any errors clearly
2. Internet access is needed once, to download the packages. After that the agent runs offline.

Manual alternative:
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Launch
- Double-click `run.bat`. It checks `.venv`, activates it and starts the agent on **http://localhost:8797** (bound to 127.0.0.1 only). Your browser opens automatically. Close the console window to stop the agent.
- Alternatively: `.venv\Scripts\python -m app.main`.

## Where data is stored
`%LOCALAPPDATA%\AIDesktopAutomationAgent\`:
- `settings.json`
- `history.sqlite3`
- `logs\agent.log`

Set `AGENT_DATA_DIR` to change this location.

## Optional: local AI
1. Install Ollama from https://ollama.com.
2. Run `ollama pull llama3.2:3b` once. This download needs internet; afterwards the model runs offline.
3. In the agent, go to **Settings → Local AI**. Keep mode `auto` or choose `ollama`, then press **Test connection**.

llama.cpp alternative: run `llama-server -m model.gguf --port 8080` and choose mode `llamacpp`. Review each model's license before redistributing it.

## Optional: executable
`build_exe.bat` builds `dist\AIDesktopAgent\AIDesktopAgent.exe` with PyInstaller. Streamlit bundles are large and slower to start, so `run.bat` remains the recommended launcher. Test the build on a clean, non-admin account.

## Tests
Run `run_tests.bat`, or:
```
.venv\Scripts\pip install pytest
.venv\Scripts\python -m pytest -q
```

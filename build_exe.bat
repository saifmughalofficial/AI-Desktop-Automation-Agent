@echo off
rem Optional: package the agent as a Windows folder app with PyInstaller.
rem run.bat remains the recommended launcher (smaller, faster to start).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install -q pyinstaller
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --name AIDesktopAgent ^
  --collect-all streamlit --collect-all pywinauto --copy-metadata streamlit ^
  --add-data "streamlit_app.py;." --add-data "app;app" --add-data "demo_workspace;demo_workspace" ^
  --add-data "docs;docs" --add-data ".streamlit;.streamlit" ^
  packaging\launcher.py
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed - see messages above.
    pause
    exit /b 1
)
echo Built: dist\AIDesktopAgent\AIDesktopAgent.exe
pause

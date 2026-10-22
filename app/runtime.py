"""Paths and environment detection shared by every layer."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"
CONFIG_DIR = APP_DIR / "config"
DOCS_DIR = PROJECT_ROOT / "docs"
DEMO_WORKSPACE = PROJECT_ROOT / "demo_workspace"
IS_WINDOWS = sys.platform == "win32"
APP_NAME = "AI Desktop Automation Agent"
LOCAL_PORT = 8797


def hosted_mode() -> bool:
    """True when running as a shared web deployment (e.g. Streamlit Community Cloud).

    A web server is shared by many visitors and cannot control anyone's desktop,
    so hosted mode gives each browser session its own sandbox copy of the demo
    workspace, keeps settings/history per session and disables app control.
    Override with AGENT_HOSTED=0/1."""
    flag = os.environ.get("AGENT_HOSTED")
    if flag is not None:
        return flag.strip().lower() in {"1", "true", "yes", "on"}
    return not IS_WINDOWS


def local_data_dir() -> Path:
    """Where settings, the SQLite history and logs live in local (desktop) mode."""
    env = os.environ.get("AGENT_DATA_DIR")
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA") if IS_WINDOWS else None
    return Path(base) / "AIDesktopAutomationAgent" if base else PROJECT_ROOT / "data"

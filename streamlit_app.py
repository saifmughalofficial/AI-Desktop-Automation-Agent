"""Alias entry point — the app lives in app.py (use either as the Streamlit main file)."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).with_name("app.py")), run_name="__main__")

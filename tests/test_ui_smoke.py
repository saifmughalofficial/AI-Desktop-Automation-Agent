"""Headless UI smoke tests (Streamlit AppTest, hosted sandbox mode): pages render and the command flow works."""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def _sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_HOSTED", "1")
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path / "data"))


def _render_page(module: str) -> None:
    import importlib

    importlib.import_module(module).render()


def test_app_starts():
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert not at.exception, [e.message for e in at.exception]


@pytest.mark.parametrize("module", ["app.ui.explorer_page", "app.ui.automation_page", "app.ui.history_page",
                                    "app.ui.settings_dialog", "app.ui.manual_page"])
def test_page_renders(module):
    at = AppTest.from_function(_render_page, args=(module,), default_timeout=90)
    at.run()
    assert not at.exception, [e.message for e in at.exception]


def test_command_preview_flow():
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    at.text_input(key="cmd_input").set_value("list the files in Downloads")
    next(b for b in at.button if b.label == "Preview").click()
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    plan = at.session_state["plan"]
    assert plan.steps and plan.steps[0].action.action == "list_files"

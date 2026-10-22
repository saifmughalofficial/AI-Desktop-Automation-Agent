"""Database initialisation, redaction, export/clear and structured logging."""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from app.config.settings import SettingsStore
from app.storage.audit_log import log_event, redact, setup_logging
from app.storage.database import Database


def test_database_initialises_schema(tmp_path):
    db = Database(tmp_path / "h.sqlite3")
    with sqlite3.connect(tmp_path / "h.sqlite3") as c:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"tasks", "actions", "meta"} <= tables
    assert db.stats()["tasks"] == 0


def test_task_roundtrip_export_and_clear(tmp_path):
    db = Database(tmp_path / "h.sqlite3")
    tid = db.create_task(request="copy x", summary="1 action", engine="rules", risk="medium", status="running",
                         approval="approved", dry_run=False, step_count=1)
    db.add_action(tid, step_index=0, action_type="copy_file", target="Demo/x", risk="medium", status="success",
                  verified=True, message="ok", undo=[{"op": "quarantine_created"}])
    db.update_task(tid, status="completed", success_count=1)
    assert db.get_task(tid)["status"] == "completed"
    assert db.undo_ops(tid) == [{"op": "quarantine_created"}]
    assert "copy_file" in db.export_text() and "copy_file" in db.export_csv()
    assert json.loads(db.export_json())[0]["actions"][0]["action_type"] == "copy_file"
    assert db.clear() == 1 and db.list_tasks() == []


def test_secrets_are_redacted_before_storage(tmp_path):
    db = Database(tmp_path / "h.sqlite3")
    tid = db.create_task(request="note password=hunter2 and token: abc123 for bob@example.com", summary="",
                         engine="rules", risk="low", status="failed", approval="n/a", dry_run=False, step_count=0)
    stored = db.get_task(tid)["request"]
    assert "hunter2" not in stored and "abc123" not in stored and "bob@example.com" not in stored


def test_redact_home_path_and_keys():
    s = redact(f"failed at {Path.home()}\\secret.txt with Bearer abc.def and sk-ABCDEFGHIJKLMNOPQRSTUV")
    assert str(Path.home()) not in s and "abc.def" not in s and "sk-ABCDEF" not in s


def test_stale_running_tasks_marked_interrupted(tmp_path):
    db = Database(tmp_path / "h.sqlite3")
    tid = db.create_task(request="x", summary="", engine="rules", risk="low", status="running", approval="",
                         dry_run=False, step_count=1)
    assert db.mark_interrupted() == 1 and db.get_task(tid)["status"] == "interrupted"


def test_history_can_be_disabled(tmp_path):
    db = Database(tmp_path / "h.sqlite3", enabled=False)
    assert db.create_task(request="x", summary="", engine="", risk="low", status="ok", approval="", dry_run=False,
                          step_count=0) is None


def test_structured_logging_writes_redacted_json(tmp_path):
    setup_logging(tmp_path / "logs")
    log_event("unit_test", secret="password=topsecret")
    for h in logging.getLogger("desktop_agent").handlers:
        h.flush()
    lines = (tmp_path / "logs" / "agent.log").read_text(encoding="utf-8").strip().splitlines()
    rec = json.loads(lines[-1])
    assert rec["event"] == "unit_test" and "topsecret" not in rec["secret"]


def test_corrupt_settings_fall_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    s = SettingsStore(path, tmp_path).load()
    assert s.approved_roots and s.approved_roots[0].alias == "Demo"

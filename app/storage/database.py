"""Local SQLite task history: tasks, per-action outcomes, approvals and undo data.

Stores summaries and outcomes only — never passwords, tokens, cookies or file contents."""
from __future__ import annotations

import csv
import io
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from app.storage.audit_log import redact

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    request TEXT NOT NULL,
    summary TEXT,
    engine TEXT,
    risk TEXT,
    status TEXT NOT NULL,
    approval TEXT,
    dry_run INTEGER DEFAULT 0,
    step_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    undone INTEGER DEFAULT 0,
    note TEXT
);
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    step_index INTEGER,
    action_type TEXT,
    target TEXT,
    risk TEXT,
    status TEXT,
    verified INTEGER DEFAULT 0,
    message TEXT,
    undo_json TEXT,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_actions_task ON actions(task_id);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""
SCHEMA_VERSION = "1"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path, enabled: bool = True):
        self.path = Path(path)
        self.enabled = enabled
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)
            c.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))

    @contextmanager
    def _conn(self):
        with self._lock:
            conn = sqlite3.connect(self.path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    # ------------------------------------------------------------------ writes
    def create_task(self, *, request: str, summary: str, engine: str, risk: str, status: str, approval: str,
                    dry_run: bool, step_count: int, note: str = "") -> int | None:
        if not self.enabled:
            return None
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO tasks(created_at, request, summary, engine, risk, status, approval, dry_run, step_count, note)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (now(), redact(request, 2000), redact(summary), engine, risk, status, approval, int(dry_run),
                 step_count, redact(note)))
            return int(cur.lastrowid)

    def update_task(self, task_id: int | None, **fields) -> None:
        if not self.enabled or task_id is None or not fields:
            return
        allowed = {"finished_at", "summary", "status", "approval", "success_count", "failed_count", "undone", "note"}
        cols = {k: (redact(v) if isinstance(v, str) and k in {"summary", "note"} else v)
                for k, v in fields.items() if k in allowed}
        sets = ", ".join(f"{k} = ?" for k in cols)
        with self._conn() as c:
            c.execute(f"UPDATE tasks SET {sets} WHERE id = ?", (*cols.values(), task_id))

    def add_action(self, task_id: int | None, *, step_index: int, action_type: str, target: str, risk: str,
                   status: str, verified: bool, message: str, undo: list | None = None,
                   started_at: str | None = None) -> None:
        if not self.enabled or task_id is None:
            return
        with self._conn() as c:
            c.execute(
                "INSERT INTO actions(task_id, step_index, action_type, target, risk, status, verified, message,"
                " undo_json, started_at, finished_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (task_id, step_index, action_type, redact(target, 400), risk, status, int(verified), redact(message),
                 json.dumps(undo) if undo else None, started_at or now(), now()))

    def clear(self) -> int:
        with self._conn() as c:
            n = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            c.execute("DELETE FROM actions")
            c.execute("DELETE FROM tasks")
            c.execute("DELETE FROM sqlite_sequence WHERE name IN ('tasks', 'actions')")
        return int(n)

    # ------------------------------------------------------------------ reads
    def list_tasks(self, limit: int = 300, status: str | None = None, search: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM tasks WHERE 1=1", []
        if status:
            sql += " AND status = ?"
            args.append(status)
        if search:
            sql += " AND (request LIKE ? OR summary LIKE ?)"
            args += [f"%{search}%", f"%{search}%"]
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def get_task(self, task_id: int) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return dict(r) if r else None

    def get_actions(self, task_id: int) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM actions WHERE task_id = ? ORDER BY step_index, id",
                                               (task_id,))]

    def undo_ops(self, task_id: int) -> list[dict]:
        ops = []
        for row in self.get_actions(task_id):
            if row["undo_json"] and row["status"] in {"success", "unverified"}:
                ops.extend(json.loads(row["undo_json"]))
        return ops

    def mark_interrupted(self) -> int:
        """Tasks left 'running'/'paused' by a previous process that stopped are recorded honestly."""
        with self._conn() as c:
            cur = c.execute("UPDATE tasks SET status = 'interrupted', finished_at = ?, note = 'App stopped before the run "
                            "finished; completed actions are listed below.' WHERE status IN ('running', 'paused')", (now(),))
            return cur.rowcount

    def approval_counts(self) -> dict:
        with self._conn() as c:
            return {r[0] or 'n/a': r[1] for r in c.execute("SELECT approval, COUNT(*) FROM tasks GROUP BY approval")}

    def last_refusal(self) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM tasks WHERE status = 'refused' ORDER BY id DESC LIMIT 1").fetchone()
            return dict(r) if r else None

    def recent_requests(self, n: int = 6) -> list[str]:
        with self._conn() as c:
            rows = c.execute("SELECT request FROM tasks WHERE engine != 'undo' AND status != 'refused' "
                             "GROUP BY request ORDER BY MAX(id) DESC LIMIT ?", (n,))
            return [r[0] for r in rows]

    def stats(self) -> dict:
        with self._conn() as c:
            by_status = {r[0]: r[1] for r in c.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")}
            act_status = {r[0]: r[1] for r in c.execute("SELECT status, COUNT(*) FROM actions GROUP BY status")}
            by_type = {r[0]: r[1] for r in c.execute(
                "SELECT action_type, COUNT(*) FROM actions GROUP BY action_type ORDER BY 2 DESC")}
        return {"tasks": sum(by_status.values()), "by_status": by_status, "actions": sum(act_status.values()),
                "action_status": act_status, "by_type": by_type}

    # ------------------------------------------------------------------ export
    def export_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["task_id", "created_at", "request", "status", "risk", "approval", "engine", "step", "action",
                    "target", "action_status", "verified", "message"])
        for t in reversed(self.list_tasks(limit=100000)):
            acts = self.get_actions(t["id"]) or [{}]
            for a in acts:
                w.writerow([t["id"], t["created_at"], t["request"], t["status"], t["risk"], t["approval"], t["engine"],
                            a.get("step_index", ""), a.get("action_type", ""), a.get("target", ""),
                            a.get("status", ""), a.get("verified", ""), a.get("message", "")])
        return buf.getvalue()

    def export_text(self) -> str:
        lines = ["AI Desktop Automation Agent — task history report", f"Generated {now()}", "=" * 60]
        for t in reversed(self.list_tasks(limit=100000)):
            lines.append(f"\n#{t['id']}  {t['created_at']}  [{t['status'].upper()}]  risk={t['risk']}  "
                         f"approval={t['approval']}  engine={t['engine']}")
            lines.append(f"  Request: {t['request']}")
            if t["summary"]:
                lines.append(f"  Summary: {t['summary']}")
            for a in self.get_actions(t["id"]):
                mark = "✓" if a["verified"] else "·"
                lines.append(f"   {mark} {a['step_index'] + 1:>2}. {a['action_type']:<16} {a['status']:<11} {a['message']}")
        return "\n".join(lines) + "\n"

    def export_json(self) -> str:
        data = [dict(t, actions=self.get_actions(t["id"])) for t in self.list_tasks(limit=100000)]
        for t in data:
            for a in t["actions"]:
                a.pop("undo_json", None)
        return json.dumps(data, indent=2, ensure_ascii=False)

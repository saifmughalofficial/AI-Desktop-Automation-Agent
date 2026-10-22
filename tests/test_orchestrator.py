"""Execution engine: approval gate, Stop between actions, conflicts, JIT confirmation, dry run, undo."""
from __future__ import annotations

import time

from app.core.action_schema import StepStatus


def run(svc, text, approved=True, **kw):
    p = svc.planner.plan(text, **kw)
    assert p.executable, (p.clarification, p.blocked_reason, p.violations)
    return svc.orchestrator.submit(p, approved=approved, background=False)


def test_approval_rejection_executes_nothing(svc, ws):
    st = run(svc, "move notes.txt to Documents", approved=False)
    assert st.status == "rejected"
    assert (ws / "Downloads" / "notes.txt").exists() and not (ws / "Documents" / "notes.txt").exists()
    assert svc.db.list_tasks()[0]["approval"] == "rejected"


def test_approved_run_is_verified_and_logged(svc, ws):
    st = run(svc, "copy all pdf files from Downloads to Documents")
    assert st.status == "completed" and all(s.verified for s in st.steps)
    acts = svc.db.get_actions(st.task_id)
    assert acts[0]["status"] == "success" and acts[0]["verified"] == 1


def test_low_risk_runs_without_approval(svc):
    st = run(svc, "list the files in Downloads", approved=False)
    assert st.status == "completed"


def test_stop_prevents_subsequent_actions(svc, ws):
    svc.settings.execution.step_delay_s = 0.4
    p = svc.planner.plan("make folders A1, A2, A3, A4, A5 in Demo")
    st = svc.orchestrator.submit(p, approved=True, background=True)
    time.sleep(0.6)
    svc.orchestrator.stop(st)
    st.thread.join(5)
    assert st.status == "cancelled"
    done = [s for s in st.steps if s.status == StepStatus.SUCCESS]
    assert 1 <= len(done) < 5
    assert all(s.status == StepStatus.CANCELLED for s in st.steps[len(done):])
    assert sum((ws / f"A{i}").is_dir() for i in range(1, 6)) == len(done)
    assert svc.db.get_task(st.task_id)["status"] == "cancelled"


def test_conflict_pauses_then_resumes(svc, ws):
    (ws / "Documents" / "notes.txt").write_text("ORIGINAL")
    st = run(svc, "copy notes.txt from Downloads to Documents")
    assert st.status == "paused" and st.pause["kind"] == "conflict"
    svc.orchestrator.resume(st, "rename", background=False)
    assert st.status == "completed"
    assert (ws / "Documents" / "notes.txt").read_text() == "ORIGINAL"
    assert (ws / "Documents" / "notes (1).txt").read_text() == "hello"


def test_conflict_stop_records_partial(svc, ws):
    (ws / "Documents" / "notes.txt").write_text("ORIGINAL")
    st = run(svc, "copy notes.txt from Downloads to Documents")
    svc.orchestrator.resume(st, "stop", background=False)
    assert st.status == "cancelled" and (ws / "Documents" / "notes.txt").read_text() == "ORIGINAL"


def test_high_risk_needs_jit_confirmation(svc, ws):
    st = run(svc, "delete notes_copy.txt")
    assert st.status == "paused" and st.pause["kind"] == "confirm"
    assert (ws / "Downloads" / "notes_copy.txt").exists()  # nothing deleted before confirmation
    svc.orchestrator.resume(st, "decline", background=False)
    assert st.status == "cancelled" and (ws / "Downloads" / "notes_copy.txt").exists()


def test_confirmed_delete_and_undo(svc, ws):
    st = run(svc, "delete notes_copy.txt")
    svc.orchestrator.resume(st, "confirm", background=False)
    assert st.status == "completed" and not (ws / "Downloads" / "notes_copy.txt").exists()
    res = svc.orchestrator.undo_task(st.task_id)
    assert res["ok"] and (ws / "Downloads" / "notes_copy.txt").read_text() == "hello"
    assert not svc.orchestrator.undo_task(st.task_id)["ok"]  # cannot undo twice


def test_dry_run_simulates_without_changes(svc, ws):
    before = sorted(p.name for p in (ws / "Downloads").iterdir())
    st = run(svc, "organize the files in Downloads by type, but don't move anything yet", approved=False)
    assert st.status == "completed" and all(s.status == StepStatus.SIMULATED for s in st.steps)
    assert sorted(p.name for p in (ws / "Downloads").iterdir()) == before


def test_runtime_recheck_and_stop_on_failure(svc, ws):
    p = svc.planner.plan("move notes.txt to Documents then move data.csv to Documents")
    (ws / "Downloads" / "notes.txt").unlink()  # disk changes after planning
    st = svc.orchestrator.submit(p, approved=True, background=False)
    assert st.steps[0].status == StepStatus.FAILED and "policy" in st.steps[0].message.lower()
    assert st.steps[1].status == StepStatus.CANCELLED and st.status == "failed"
    assert (ws / "Downloads" / "data.csv").exists()


def test_undo_organize_restores_layout(svc, ws):
    before = sorted(p.name for p in (ws / "Downloads").iterdir())
    st = run(svc, "organize the files in Downloads by type")
    assert st.status == "completed"
    res = svc.orchestrator.undo_task(st.task_id)
    assert res["ok"]
    assert sorted(p.name for p in (ws / "Downloads").iterdir() if p.name != ".agent_trash") == before

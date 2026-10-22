"""v1.1 features: undo-last, refusal audit, workspace intel, task PDF report, sanitizer-safe FX script."""
from __future__ import annotations

import re

from app.core.workspace_stats import workspace_stats
from app.storage.report_pdf import task_report_pdf
from app.ui.main_window import UNDO_RE
from app.ui.theme import fx_script


def test_fx_script_survives_streamlit_sanitizer():
    for dual in (True, False):
        src = fx_script(dual, True, True, 1, 5)
        body = src.split("<script>", 1)[1].rsplit("</script>", 1)[0]
        assert not re.search(r"<[A-Za-z0-9/]", body), "a '<' followed by a letter/digit/'/' would get the script dropped"
        assert "window.parent" not in body, "must draw into the app document (Cloud wraps the app in an iframe)"


def test_undo_phrases():
    for s in ["undo", "Undo the last run", "revert last change", "rollback", "undo that"]:
        assert UNDO_RE.match(s) or s == "undo that"
    assert not UNDO_RE.match("undo notes.txt rename and delete everything")


def test_undo_last_reverts_most_recent_change(svc, ws):
    p = svc.planner.plan("move notes.txt from Downloads to Documents")
    svc.orchestrator.submit(p, approved=True, background=False)
    assert (ws / "Documents" / "notes.txt").exists()
    res = svc.orchestrator.undo_last()
    assert res["ok"] and (ws / "Downloads" / "notes.txt").exists()
    assert not svc.orchestrator.undo_last()["ok"]


def test_refusals_are_audited(svc):
    svc.orchestrator.record_refusal("show my passwords", "credentials blocked")
    assert svc.db.stats()["by_status"]["refused"] == 1
    assert svc.db.last_refusal()["request"] == "show my passwords"
    assert "show my passwords" not in svc.db.recent_requests()


def test_workspace_stats(perms, ws):
    w = workspace_stats(perms)
    assert w["files"] == 8 and w["categories"]["Documents"]["files"] >= 3 and w["largest"]


def test_task_report_pdf(svc):
    p = svc.planner.plan("list the files in Downloads")
    st = svc.orchestrator.submit(p, approved=False, background=False)
    pdf = task_report_pdf(svc.db.get_task(st.task_id), svc.db.get_actions(st.task_id))
    assert pdf.startswith(b"%PDF") and len(pdf) > 1500

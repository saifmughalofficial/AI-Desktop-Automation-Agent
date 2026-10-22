"""History: every task, its approval decision and per-action outcomes; undo, export, clear."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from app.storage.report_pdf import task_report_pdf
from app.ui import components as C
from app.ui import state


def render() -> None:
    s = state.svc()
    db = s.db
    st.markdown(C.page_title("Activity & History", "Local SQLite audit trail · approvals · outcomes · undo",
                             "history"), unsafe_allow_html=True)
    if not db.enabled:
        st.markdown(C.callout("warn", "<b>History recording is disabled</b> (Settings → Workspace). Existing "
                                      "records are still shown."), unsafe_allow_html=True)
    stats = db.stats()
    by = stats["by_status"]
    done = by.get("completed", 0)
    total = stats["tasks"]
    m = st.columns(5)
    m[0].metric("Tasks", total)
    m[1].metric("Completed", done)
    m[2].metric("Partial / failed", by.get("partial", 0) + by.get("failed", 0))
    m[3].metric("Rejected / refused", by.get("rejected", 0) + by.get("refused", 0))
    m[4].metric("Actions run", stats["actions"])

    if stats["by_type"]:
        top = max(stats["by_type"].values())
        bars = "".join(C.task_bar(k, v / top * 100, str(v)) for k, v in list(stats["by_type"].items())[:8])
        st.markdown(C.panel("Actions by type", "chart", bars), unsafe_allow_html=True)

    c1, c2 = st.columns([1, 2])
    status = c1.selectbox("Status", ["all", "completed", "partial", "failed", "cancelled", "rejected", "refused", "interrupted", "paused", "running"])
    search = c2.text_input("Search requests", placeholder="e.g. rename")
    tasks = db.list_tasks(status=None if status == "all" else status, search=search or None)
    if not tasks:
        st.markdown("<div class='empty'>No tasks recorded yet. Run something from the Command Center.</div>",
                    unsafe_allow_html=True)
    else:
        df = pd.DataFrame(tasks)[["id", "created_at", "request", "status", "risk", "approval", "engine",
                                  "success_count", "failed_count", "undone"]]
        df.columns = ["#", "When", "Request", "Status", "Risk", "Approval", "Engine", "OK", "Failed", "Undone"]
        st.dataframe(df, hide_index=True, width="stretch", height=min(380, 38 + 35 * len(df)))

        ids = [t["id"] for t in tasks]
        pick = st.selectbox("Task details", ids, format_func=lambda i: f"#{i} — {next(t['request'] for t in tasks if t['id'] == i)[:80]}")
        task = db.get_task(pick)
        acts = db.get_actions(pick)
        st.markdown(C.callout({"completed": "ok", "rejected": "bad", "failed": "bad"}.get(task["status"], "warn"),
                              f"<b>#{task['id']} · {task['status'].upper()}</b> · risk {task['risk']} · approval "
                              f"{task['approval']} · {task['summary'] or ''}"), unsafe_allow_html=True)
        if acts:
            adf = pd.DataFrame(acts)[["step_index", "action_type", "target", "status", "verified", "message", "finished_at"]]
            adf["step_index"] = adf["step_index"] + 1
            adf["verified"] = adf["verified"].map({1: "✓", 0: "—"})
            adf.columns = ["Step", "Action", "Target", "Status", "Verified", "Message", "Finished"]
            st.dataframe(adf, hide_index=True, width="stretch")
        can_undo = bool(db.undo_ops(pick)) and not task["undone"]
        b1, b2 = st.columns(2)
        b2.download_button("Task report (PDF)", task_report_pdf(task, acts), f"task_{pick}_report.pdf", "application/pdf",
                           icon=":material/picture_as_pdf:", width="stretch", key=f"pdf_{pick}")
        if b1.button("Undo this task's file changes", icon=":material/undo:", disabled=not can_undo, width="stretch"):
            res = s.orchestrator.undo_task(pick)
            (st.success if res["ok"] else st.warning)(res["message"])
            state.push_event("OK" if res["ok"] else "WARN", res["message"])
        if not can_undo:
            st.caption("Undo is available for tasks that changed files and have not been undone yet. It never "
                       "overwrites and skips anything modified since.")

    st.divider()
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    e1, e2, e3, e4 = st.columns(4)
    e1.download_button("Export report (.txt)", db.export_text(), f"agent_history_{stamp}.txt", "text/plain",
                       icon=":material/description:", width="stretch")
    e2.download_button("Export CSV", db.export_csv(), f"agent_history_{stamp}.csv", "text/csv",
                       icon=":material/table:", width="stretch")
    e3.download_button("Export JSON", db.export_json(), f"agent_history_{stamp}.json", "application/json",
                       icon=":material/data_object:", width="stretch")
    with e4.popover("Clear history", icon=":material/delete_sweep:", width="stretch"):
        st.write("Permanently delete all task records? Files are not affected, but Undo data is lost.")
        if st.button("Yes, clear history", type="primary"):
            n = db.clear()
            state.push_event("WARN", f"History cleared ({n} task(s)).")
            st.rerun()

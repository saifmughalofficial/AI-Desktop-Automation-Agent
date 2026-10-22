"""Approval gate: shows exact targets and consequences before anything sensitive runs."""
from __future__ import annotations

import streamlit as st

from app.core.action_schema import Plan, Risk
from app.ui import components as C
from app.ui import state
from app.ui.theme import esc


def start_run(plan: Plan, approved: bool) -> None:
    s = state.svc()
    run = s.orchestrator.submit(plan, approved=approved, background=True)
    state.set_run(run)
    st.session_state._was_running = True
    state.push_event("RUN" if run.status == "running" else "WARN", run.log[-1][2] if run.log else run.status)


@st.dialog("Approval required", width="large")
def approval_dialog(plan: Plan) -> None:
    high = plan.risk == Risk.HIGH
    st.html(C.callout("bad" if high else "warn",
                      f"<b>{esc(plan.summary)}</b> &nbsp; {C.risk_badge(plan.risk.value)}<br>"
                      "Review the exact targets below. Nothing runs until you approve. "
                      "You can press <b>STOP</b> at any time; it takes effect between actions."))
    rows = []
    for s_ in plan.steps[:80]:
        rows.append(f"<tr><td>{s_.index + 1}</td><td><b>{esc(s_.description)}</b>"
                    f"<div class='sub'>{esc(s_.consequence)}</div>"
                    + (f"<div class='warn'>⚠ {esc(s_.conflict)}</div>" if s_.conflict else "")
                    + (f"<div class='bad'>Requires a second confirmation right before it runs.</div>"
                       if s_.requires_confirmation else "")
                    + f"</td><td>{C.risk_badge(s_.risk.value)}</td></tr>")
    more = f"<div class='sub'>…and {len(plan.steps) - 80} more</div>" if len(plan.steps) > 80 else ""
    st.html("<table class='steps'><tr><th>#</th><th>EXACT ACTION &amp; CONSEQUENCE</th><th>RISK</th></tr>"
            + "".join(rows) + "</table>" + more)
    if plan.conflicts:
        st.html(C.callout("warn", "<b>Name conflicts detected.</b> Existing files are never overwritten — the run "
                                  "will pause at each conflict and ask you to skip, keep both or stop."))
    ok = True
    if high:
        st.html(C.callout("bad", "<b>High-risk plan.</b> Deleted items go to the <code>.agent_trash</code> quarantine "
                                 "(restorable with Undo), and each high-risk step asks again just before it runs."))
        ack = st.checkbox("I understand exactly which items will be affected.", key="ack_high")
        typed = st.text_input("Type APPROVE to continue", key="ack_word", placeholder="APPROVE")
        ok = ack and typed.strip().upper() == "APPROVE"
    c1, c2 = st.columns(2)
    if c1.button("Approve & run", type="primary", width="stretch", disabled=not ok, icon=":material/verified:"):
        start_run(plan, approved=True)
        st.rerun()
    if c2.button("Reject", width="stretch", icon=":material/block:"):
        state.svc().orchestrator.reject(plan)
        state.push_event("WARN", "Plan rejected by user — nothing executed.")
        state.set_plan(None)
        st.rerun()

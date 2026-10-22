"""Command Center: HUD dashboard + task input, plan preview, approval and live execution."""
from __future__ import annotations

import re
import time

import pandas as pd
import streamlit as st

from app.actions import ui_automation
from app.core.action_schema import ACTION_NAMES, Plan, StepStatus
from app.core.workspace_stats import workspace_stats
from app.llm.rules_fallback import EXAMPLES
from app.ui import components as C
from app.ui import state
from app.ui.approval_dialog import approval_dialog, start_run
from app.ui.theme import brain_html, esc, header_html
from app.ui.virtual_apps import render_virtual_desktop

RUNNING = {"running", "queued"}
UNDO_RE = re.compile(r"^\s*(?:please\s+)?(?:undo|revert|roll ?back)(?:\s+(?:the|my))?(?:\s+(?:last|previous|latest))?"
                     r"(?:\s+(?:run|task|change|changes|action|actions|operation))?\s*[.!]?\s*$", re.I)
CAT_COLORS = {"Images": "#38bdf8", "Documents": "#a855f7", "Code": "#22d3ee", "Archives": "#fbbf24",
              "Audio": "#34d399", "Video": "#fb7185", "Other": "#94a3b8"}


def engine_label(s) -> str:
    mode = s.settings.llm.mode
    if mode == "rules":
        return "RULES ENGINE"
    st_ = s.llm.status()
    if st_.get("available"):
        return f"{st_['backend'].upper()} · {st_.get('model', '')}".upper()
    return "RULES ENGINE · AI OFFLINE" if mode == "auto" else f"{mode.upper()} OFFLINE → RULES"


def env_label(s) -> str:
    return "HOSTED SANDBOX" if s.hosted else "LOCAL · WINDOWS"


@st.cache_resource(show_spinner=False)
def _uia_status() -> tuple[bool, str]:
    return ui_automation.available()


# --------------------------------------------------------------------------- header + command bar
def render_header() -> None:
    s = state.svc()
    st.iframe(header_html(engine_label(s), env_label(s), s.settings.animations, s.settings.theme == "dual"), height=70)


def _on_example() -> None:
    choice = st.session_state.get("example_pick")
    if choice:
        st.session_state.cmd_input = choice
        st.session_state.example_pick = None


def _apply_answer(kind: str) -> None:
    plan = state.get_plan()
    ans = (st.session_state.get("clarify_answer") or "").strip()
    if not plan or not ans:
        return
    joiner = {"location": " in ", "destination": " to ", "source": " from ", "name": " named "}.get(kind, " ")
    st.session_state.cmd_input = f"{plan.request.rstrip(' .')}{joiner}{ans}"
    st.session_state.auto_cmd = "preview"
    st.session_state.clarify_answer = ""


def command_bar() -> None:
    s = state.svc()
    busy = state.run_is_active()
    st.markdown('<div class="cmd-box">', unsafe_allow_html=True)
    with st.form("cmd_form", clear_on_submit=False, border=False):
        c1, c2, c3 = st.columns([7.4, 1.25, 1.25], vertical_alignment="bottom")
        text = c1.text_input("Command", key="cmd_input", label_visibility="collapsed",
                             placeholder="Ask the agent…  e.g. “Create a folder named Reports in my Projects directory”")
        preview = c2.form_submit_button("Preview", icon=":material/visibility:", width="stretch", disabled=busy)
        run = c3.form_submit_button("Run", icon=":material/play_arrow:", type="primary", width="stretch", disabled=busy)
    st.markdown('</div>', unsafe_allow_html=True)
    st.pills("Examples", EXAMPLES, key="example_pick", on_change=_on_example, label_visibility="collapsed")

    auto = st.session_state.pop("auto_cmd", None)
    if auto and not busy:
        preview, run, text = auto == "preview", auto == "run", st.session_state.get("cmd_input", "")
    if (preview or run) and UNDO_RE.match(text or ""):
        _undo_last()
    elif (preview or run) and text.strip():
        plan = state.make_plan(text)
        if run and plan.executable:
            if s.policy.approval_required(plan):
                approval_dialog(plan)
            else:
                start_run(plan, approved=False)
                st.rerun()
    elif (preview or run) and not text.strip():
        st.toast("Type a task first — or pick one of the examples.", icon=":material/keyboard:")

    note = st.session_state.pop("notice", None)
    if note:
        st.markdown(C.callout("ok" if note[0] else "warn", f"<b>{esc(note[1])}</b>"), unsafe_allow_html=True)
    sel, ctx = state.selection(), state.context_folder()
    if sel or ctx:
        cols = st.columns([8, 1.4])
        chips = ""
        if ctx:
            chips += C.chip(f"📁 Context folder: {ctx.display()}")
        if sel:
            names = ", ".join(r.name for r in sel[:4]) + (f" +{len(sel) - 4}" if len(sel) > 4 else "")
            chips += C.chip(f"☑ {len(sel)} selected: {names}")
        cols[0].markdown(chips, unsafe_allow_html=True)
        if cols[1].button("Clear context", icon=":material/close:", width="stretch"):
            st.session_state.selection = []
            st.session_state.context_folder = None
            st.rerun()


def _undo_last() -> None:
    res = state.svc().orchestrator.undo_last()
    state.push_event("OK" if res["ok"] else "WARN", res["message"])
    st.session_state.notice = (res["ok"], res["message"])
    st.toast(res["message"], icon=":material/undo:")


# --------------------------------------------------------------------------- plan panel
def _help_panel() -> None:
    rows = "".join(f"<li><code>{esc(e)}</code></li>" for e in EXAMPLES)
    body = ("<div style='font-size:.92rem'>The agent understands these kinds of tasks without any AI model "
            "(rules engine). Every plan is shown before it runs; risky ones need your approval.</div>"
            f"<ul style='margin:.5rem 0 0 1rem;font-size:.9rem'>{rows}</ul>"
            "<div style='font-size:.85rem;color:#7ea6cc;margin-top:6px'>Chain steps with <b>then</b>. Say "
            "<b>preview</b> or <b>show me first</b> for a dry run. Full reference: Manual page.</div>")
    st.markdown(C.panel("Supported commands", "book", body), unsafe_allow_html=True)


def plan_panel(plan: Plan, actions: bool = True) -> None:
    s = state.svc()
    if plan.help:
        _help_panel()
        return
    if plan.blocked_reason:
        st.markdown(C.panel("Request refused by policy", "shield",
                            C.callout("bad", f"<b>Not executed.</b> {esc(plan.blocked_reason)}")
                            + "<div style='font-size:.86rem;color:#7ea6cc'>The policy engine screens every request "
                              "before planning. See Manual → Safety for what the agent will never do.</div>"),
                    unsafe_allow_html=True)
        if st.button("Dismiss", icon=":material/close:"):
            state.set_plan(None)
            st.rerun()
        return
    if plan.clarification:
        st.markdown(C.panel("Clarification needed", "eye",
                            C.callout("warn", f"<b>I need a bit more detail before planning.</b><br>{esc(plan.clarification)}")
                            + "".join(C.callout("info", esc(n)) for n in plan.notes)),
                    unsafe_allow_html=True)
        kind = plan.clarification_kind
        hint = {"location": "Folder name, e.g. Photos", "destination": "Destination folder, e.g. Documents",
                "source": "Source folder, e.g. Downloads", "name": "Name, e.g. Reports"}.get(kind, "Rephrase the task")
        if kind == "generic":
            st.caption("Edit the command above and press Preview again.")
        else:
            c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
            c1.text_input("Your answer", key="clarify_answer", placeholder=hint)
            c2.button("Answer", type="primary", width="stretch", on_click=_apply_answer, args=(kind,))
        if st.button("Dismiss", icon=":material/close:", key="dismiss_clar"):
            state.set_plan(None)
            st.rerun()
        return

    head = (f"<div class='plan-head'><span class='sum'>{esc(plan.summary)}</span>{C.risk_badge(plan.risk.value)}"
            f"{C.chip('engine: ' + plan.engine)}"
            + (C.chip("DRY RUN") if plan.dry_run else "")
            + (C.chip("approval required") if plan.requires_approval else C.chip("no approval needed"))
            + "</div>")
    blocks = [head]
    for a in plan.assumptions:
        blocks.append(C.callout("info", f"<b>Assumption:</b> {esc(a)}"))
    for n in plan.notes:
        blocks.append(C.callout("info", esc(n)))
    for v in plan.violations:
        blocks.append(C.callout("bad", f"<b>Blocked:</b> {esc(v)}"))
    for c in plan.conflicts:
        blocks.append(C.callout("warn", f"<b>Conflict:</b> {esc(c)}"))
    rows = []
    for s_ in plan.steps[:100]:
        extra = ""
        if s_.violation:
            extra += f"<div class='bad'>✕ {esc(s_.violation)}</div>"
        if s_.conflict:
            extra += f"<div class='warn'>⚠ {esc(s_.conflict)}</div>"
        if s_.note:
            extra += f"<div class='sub'>ℹ {esc(s_.note)}</div>"
        rows.append(f"<tr style='animation-delay:{min(s_.index, 12) * 0.04:.2f}s'><td>{s_.index + 1:02d}</td>"
                    f"<td><b>{esc(s_.description)}</b><div class='sub'>Expect: {esc(s_.expected)}</div>"
                    f"<div class='sub'>Verify: {esc(s_.verification)}</div>{extra}</td>"
                    f"<td>{C.risk_badge(s_.risk.value)}{'<div class=sub>confirm</div>' if s_.requires_confirmation else ''}</td></tr>")
    blocks.append("<table class='steps'><tr><th>#</th><th>ACTION · EXPECTED RESULT · VERIFICATION</th><th>RISK</th></tr>"
                  + "".join(rows) + "</table>")
    if len(plan.steps) > 100:
        blocks.append(f"<div class='sub'>…and {len(plan.steps) - 100} more step(s).</div>")
    if plan.preconditions:
        blocks.append("<div style='font-size:.84rem;color:#7ea6cc;margin-top:6px'><b>Preconditions:</b> "
                      + " · ".join(esc(p) for p in plan.preconditions) + "</div>")
    st.markdown(C.panel("Execution plan", "plan", "".join(blocks), meta=f"{len(plan.steps)} step(s)"),
                unsafe_allow_html=True)

    if not actions:
        return
    busy = state.run_is_active()
    c1, c2, c3 = st.columns([1.6, 1.4, 1])
    dry = c2.toggle("Dry run (simulate only)", value=plan.dry_run, key=f"dry_{id(plan)}", disabled=busy)
    if dry != plan.dry_run:
        plan.dry_run = dry
        s.policy.evaluate(plan)
        if dry and "dry run" not in plan.summary:
            plan.summary += " — preview only (dry run)"
        if not dry:
            plan.summary = plan.summary.replace(" — preview only (dry run)", "")
        st.rerun()
    label = "Simulate plan" if plan.dry_run else ("Review & approve" if plan.requires_approval else "Execute plan")
    if c1.button(label, type="primary", icon=":material/rocket_launch:", width="stretch",
                 disabled=busy or not plan.executable):
        if s.policy.approval_required(plan):
            approval_dialog(plan)
        else:
            start_run(plan, approved=False)
            st.rerun()
    if c3.button("Cancel", icon=":material/close:", width="stretch", disabled=busy):
        state.set_plan(None)
        state.push_event("INFO", "Plan discarded — nothing executed.")
        st.rerun()


# --------------------------------------------------------------------------- execution panel
def _execute_for_real(plan: Plan) -> None:
    s = state.svc()
    fresh = s.planner.plan(plan.request, selection=state.selection(), current=state.context_folder())
    fresh.dry_run = False
    fresh.summary = fresh.summary.replace(" — preview only (dry run)", "")
    s.policy.evaluate(fresh)
    state.set_plan(fresh)
    state.set_run(None)
    state.push_event("INFO", "Dry run reviewed — real plan prepared; approval follows.")


def execution_panel() -> None:
    run = state.get_run()
    live = bool(run and run.status in RUNNING)

    @st.fragment(run_every=0.6 if live else None)
    def _live() -> None:
        s = state.svc()
        r = state.get_run()
        if not r:
            return
        done = r.done
        title = {"running": "Executing", "paused": "Paused — your decision needed", "queued": "Queued"}.get(
            r.status, f"Run {r.status}")
        body = [C.progress(r.progress, done)]
        if r.summary:
            tone = {"completed": "ok", "partial": "warn", "failed": "bad", "cancelled": "warn", "rejected": "bad"}.get(r.status, "info")
            body.append(C.callout(tone, f"<b>{esc(r.summary)}</b>"))
        for ss in r.steps[:60]:
            body.append(C.step_row(ss.index + 1, ss.description, ss.status.value, ss.message))
        if len(r.steps) > 60:
            body.append(f"<div class='sub'>…{len(r.steps) - 60} more step(s)</div>")
        st.markdown(C.panel(title, "exec", "".join(body), meta=f"run {r.id}" + (" · DRY RUN" if r.dry_run else "")),
                    unsafe_allow_html=True)
        if r.status == "paused" and r.pause:
            kind = r.pause["kind"]
            st.markdown(C.callout("warn" if kind == "conflict" else "bad", f"<b>{esc(r.pause['message'])}</b>"),
                        unsafe_allow_html=True)
            opts = {"confirm": ("Confirm this step", ":material/check:", "primary"),
                    "decline": ("Decline & stop", ":material/block:", "secondary"),
                    "skip": ("Skip this item", ":material/redo:", "secondary"),
                    "rename": ("Keep both (auto-rename)", ":material/content_copy:", "primary"),
                    "stop": ("Stop the run", ":material/stop_circle:", "secondary")}
            cols = st.columns(len(r.pause["options"]))
            for col, opt in zip(cols, r.pause["options"]):
                label, ico, typ = opts[opt]
                if col.button(label, icon=ico, type=typ, width="stretch", key=f"res_{r.id}_{opt}_{r.pause['step']}"):
                    s.orchestrator.resume(r, opt)
                    state.push_event("INFO", f"Run {r.id}: user chose '{opt}'.")
                    st.session_state._was_running = True
                    st.rerun()
        if not done:
            st.markdown('<div class="stop-btn">', unsafe_allow_html=True)
            if st.button("STOP — emergency halt", icon=":material/dangerous:", width="stretch", key=f"stop_{r.id}"):
                s.orchestrator.stop(r)
                state.push_event("WARN", f"Run {r.id}: STOP pressed.")
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        if done and st.session_state.get("_was_running"):
            st.session_state._was_running = False
            state.push_event("DONE", r.summary)
            st.rerun(scope="app")

    _live()
    if run and run.done:
        _run_results(run)


def _run_results(run) -> None:
    for ss in run.steps:
        rows = ss.details.get("rows") if ss.details else None
        if rows:
            with st.expander(f"Result · step {ss.index + 1}: {ss.description}", expanded=len(run.steps) <= 3):
                df = pd.DataFrame(rows)
                keep = [c for c in ("name", "relative", "kind", "category", "size_h", "modified", "group", "file",
                                    "control_type", "automation_id", "enabled") if c in df.columns]
                st.dataframe(df[keep] if keep else df, hide_index=True, width="stretch", height=min(420, 38 + 35 * len(df)))
    c1, c2, c3 = st.columns(3)
    if run.dry_run and run.status == "completed" and any(s.status == StepStatus.SIMULATED for s in run.steps):
        if c1.button("Run for real", type="primary", icon=":material/bolt:", width="stretch"):
            _execute_for_real(run.plan)
            st.rerun()
    if run.task_id and not run.dry_run and state.svc().db.undo_ops(run.task_id):
        if c2.button("Undo this run", icon=":material/undo:", width="stretch"):
            res = state.svc().orchestrator.undo_task(run.task_id)
            state.push_event("OK" if res["ok"] else "WARN", res["message"])
            st.toast(res["message"], icon=":material/undo:")
    if c3.button("New task", icon=":material/add:", width="stretch"):
        state.set_run(None)
        state.set_plan(None)
        st.rerun()


# --------------------------------------------------------------------------- HUD
def _flow_stage() -> str | None:
    run, plan = state.get_run(), state.get_plan()
    if run and run.status == "running":
        return "EXECUTOR"
    if run and run.status == "paused":
        return "POLICY"
    if run and run.done:
        return "AUDIT"
    if plan and (plan.steps or plan.clarification):
        return "POLICY" if plan.steps else "PLANNER"
    return "INPUT"


def hud_left() -> None:
    s = state.svc()
    m = s.monitor.sample(s.workspace)
    if m.get("ok"):
        g = (C.gauge("CPU", m["cpu"], f"{m['cores']} threads") + C.gauge("RAM", m["mem"], C.human_bytes(m["mem_used"]))
             + C.gauge("DISK", m["disk"], C.human_bytes(m["disk_total"] - m["disk_used"]) + " free"))
    else:
        g = C.gauge("CPU", None, "psutil missing") + C.gauge("RAM", None) + C.gauge("DISK", None)
    st.markdown(C.panel("System performance", "cpu", f"<div class='gauges'>{g}</div>"), unsafe_allow_html=True)
    load = max(m.get("cpu", 0), m.get("mem", 0)) if m.get("ok") else 0
    status = ("System status: optimal", "") if load < 80 else ("System status: high load", "amber")
    run = state.get_run()
    if run and run.status == "paused":
        status = ("Agent paused — awaiting your decision", "amber")
    st.markdown(C.panel("Agent data flow", "flow", C.dataflow(_flow_stage()) + C.status_line(*status)),
                unsafe_allow_html=True)


def hud_center() -> None:
    s = state.svc()
    run = state.get_run()
    llm = s.llm.status() if s.settings.llm.mode != "rules" else {"available": False, "detail": "Disabled (rules-only)"}
    uia_ok, uia_msg = _uia_status()
    stats = s.db.stats()
    running = bool(run and run.status == "running")
    rows = [
        C.agent_row("Rules parser", "Offline natural-language commands", "Active", "", "rules", 100),
        C.agent_row("Local LLM", (llm.get("detail") or "")[:48], "Online" if llm.get("available") else "Offline",
                    "" if llm.get("available") else "off", "model", 100 if llm.get("available") else 8),
        C.agent_row("Policy engine", "Risk · approvals · sandbox", "Armed", "", "shield", 100),
        C.agent_row("Executor", f"{len(ACTION_NAMES)} registered actions",
                    "Running" if running else ("Paused" if run and run.status == "paused" else "Idle"),
                    "amber" if run and not run.done else "", "exec",
                    (run.progress * 100) if run else 0, running=running),
        C.agent_row("UI automation", (uia_msg if not s.hosted else "Web virtual desktop (cloud sandbox)")[:48],
                    "Ready" if uia_ok or s.hosted else "Off", "" if uia_ok or s.hosted else "off", "eye",
                    100 if uia_ok or s.hosted else 8),
        C.agent_row("Audit log", f"{stats['tasks']} tasks · {stats['actions']} actions",
                    "Recording" if s.db.enabled else "Disabled", "" if s.db.enabled else "off", "log", 100),
    ]
    st.markdown(C.panel("AI agents", "brain", "".join(rows)), unsafe_allow_html=True)
    lines = list(run.log) if run else list(state.events())
    st.markdown(C.panel("Command terminal", "terminal", C.terminal(lines), meta=f"run {run.id}" if run else "events"),
                unsafe_allow_html=True)


def hud_right() -> None:
    s = state.svc()
    m = s.monitor.sample(s.workspace)
    if m.get("ok"):
        charts = (C.area_chart("CPU usage", list(s.monitor.cpu), f"{m['cpu']:.0f}%", "#22d3ee", 100)
                  + C.area_chart("Memory usage", list(s.monitor.mem), f"{m['mem']:.0f}%", "#34d399", 100)
                  + C.area_chart("Network", list(s.monitor.net), f"{m['net_kbs'] / 1024:.2f} MB/s" if m["net_kbs"] > 1024
                                 else f"{m['net_kbs']:.0f} KB/s", "#a78bfa"))
        kv = (f"<b>{C.human_bytes(m['disk_used'])}</b> / {C.human_bytes(m['disk_total'])}<br>"
              f"Read&nbsp; <b>{C.human_bytes(m['read_bs'])}/s</b><br>Write <b>{C.human_bytes(m['write_bs'])}/s</b>")
        storage = C.donut(m["disk"], kv)
    else:
        charts, storage = "<div class='empty'>Install psutil for live metrics.</div>", ""
    st.markdown(C.panel("Resource usage", "chart", charts), unsafe_allow_html=True)
    st.markdown(C.panel("Storage", "disk", storage, meta="workspace drive"), unsafe_allow_html=True)
    run = state.get_run()
    if run and not run.done:
        items = [C.task_bar(f"{ss.index + 1}. {ss.description}", 100 if ss.status.value not in {"pending", "running", "paused"} else
                            (55 if ss.status.value == "running" else 4), ss.status.value, running=ss.status.value == "running")
                 for ss in run.steps if ss.status.value in {"running", "paused", "pending"}][:4]
        body = C.task_bar("Overall progress", run.progress * 100, f"{run.progress * 100:.0f}%", running=True) + "".join(items)
    else:
        recent = s.db.list_tasks(limit=4)
        if recent:
            body = "".join(C.task_bar(f"#{t['id']} {t['request'][:38]}", 100 if t["status"] in {"completed"} else 60,
                                      t["status"]) for t in recent)
        else:
            body = "<div class='empty'>No tasks yet. Try an example command above.</div>"
    st.markdown(C.panel("Active tasks", "tasks", body), unsafe_allow_html=True)


def _stats(s) -> dict:
    cache = st.session_state.get("_ws_stats")
    run = state.get_run()
    stamp = (run.id, run.status) if run else None
    if cache and time.monotonic() - cache[0] < 20 and cache[1] == stamp:
        return cache[2]
    data = workspace_stats(s.perms)
    st.session_state._ws_stats = (time.monotonic(), stamp, data)
    return data


def intel_row() -> None:
    s = state.svc()
    w = _stats(s)
    c1, c2, c3 = st.columns([1.25, 1, 1])
    with c1:
        top = max([v["files"] for v in w["categories"].values()] or [1])
        bars = "".join(
            f"<div class='task'><div class='hd'><span><i class='swatch' style='background:{CAT_COLORS.get(k, '#94a3b8')}'></i>{esc(k)}</span>"
            f"<span>{v['files']} · {C.human_bytes(v['bytes'])}</span></div><div class='bar'><i style='width:{v['files'] / top * 100:.0f}%;"
            f"background:{CAT_COLORS.get(k, '#94a3b8')};box-shadow:0 0 8px {CAT_COLORS.get(k, '#94a3b8')}'></i></div></div>"
            for k, v in w["categories"].items())
        tiles = "".join(f"<div class='tile'><b>{v}</b><span>{k}</span></div>" for k, v in
                        [("Files", w["files"]), ("Folders", w["folders"]), ("Size", C.human_bytes(w["bytes"])),
                         ("Quarantined", w["quarantined"])])
        big = "".join(f"<div class='mini'>▸ {esc(p)} <em>{C.human_bytes(n)}</em></div>" for n, p in w["largest"])
        st.markdown(C.panel("Workspace intel", "folder", f"<div class='tiles'>{tiles}</div>{bars}"
                            f"<div class='mini-h'>Largest files</div>{big or '<div class=empty>No files</div>'}",
                            meta=f"{w['roots']} approved folder(s)"), unsafe_allow_html=True)
    with c2:
        ap = s.db.approval_counts()
        by = s.db.stats()["by_status"]
        tiles = "".join(f"<div class='tile {cls}'><b>{n}</b><span>{lbl}</span></div>" for lbl, n, cls in [
            ("Approved", ap.get("approved", 0), "ok"), ("Auto (low risk)", ap.get("not required", 0), ""),
            ("Dry runs", ap.get("dry-run", 0), "vi"), ("Rejected", ap.get("rejected", 0), "warn"),
            ("Refused", by.get("refused", 0), "bad"), ("Undone", sum(1 for t in s.db.list_tasks(limit=500) if t["undone"]), "")])
        last = s.db.last_refusal()
        tail = (C.callout("bad", f"<b>Last refusal:</b> “{esc(last['request'][:70])}” — {esc(last['summary'][:110])}")
                if last else "<div class='empty'>No requests refused yet. Try “show my saved passwords”.</div>")
        st.markdown(C.panel("Policy shield", "shield", f"<div class='tiles t3'>{tiles}</div>{tail}"), unsafe_allow_html=True)
    with c3:
        st.markdown(C.panel("Quick relaunch", "history", "<div class='mini-h'>Recent commands — one click to preview again</div>"),
                    unsafe_allow_html=True)
        recent = s.db.recent_requests(5)
        busy = state.run_is_active()
        for i, cmd in enumerate(recent):
            if st.button(cmd[:58] + ("…" if len(cmd) > 58 else ""), key=f"recent_{i}", icon=":material/replay:",
                         width="stretch", disabled=busy):
                state.queue_command(cmd, "preview")
                st.rerun()
        if not recent:
            st.caption("Your recent commands will appear here.")
        if st.button("Undo last run", icon=":material/undo:", width="stretch", disabled=busy, key="undo_last_btn"):
            _undo_last()
            st.rerun()


def render() -> None:
    s = state.svc()
    render_header()
    command_bar()
    plan, run = state.get_plan(), state.get_run()
    if plan or run:
        if run and plan and not run.done:
            c1, c2 = st.columns([1.15, 1])
            with c1:
                plan_panel(plan)
            with c2:
                execution_panel()
        elif run:
            c1, c2 = st.columns([1.15, 1])
            with c1:
                if plan:
                    plan_panel(plan, actions=False)
                else:
                    st.markdown(C.panel("Execution plan", "plan", "<div class='empty'>Plan finished.</div>"),
                                unsafe_allow_html=True)
            with c2:
                execution_panel()
        else:
            plan_panel(plan)

    render_virtual_desktop()
    refresh = 2.5 if s.settings.animations else 6
    left, center, right = st.columns([1, 1.38, 1])
    with left:
        st.fragment(run_every=refresh)(hud_left)()
    with center:
        st.iframe(brain_html("AI CORE · ONLINE", f"{len(ACTION_NAMES)} REGISTERED ACTIONS · SANDBOXED",
                                   s.settings.animations, dual=s.settings.theme == "dual"), height=334)
        st.fragment(run_every=refresh)(hud_center)()
    with right:
        st.fragment(run_every=refresh)(hud_right)()
    intel_row()

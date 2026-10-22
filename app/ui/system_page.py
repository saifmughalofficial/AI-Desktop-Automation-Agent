"""System Manager page: live health, processes, disks, network, services, startup,
Windows settings shortcuts, media/volume and power — all policy-checked."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.core.system_manager import MEDIA_KEYS, POWER_LABELS, SETTINGS_PAGES, SystemManager
from app.ui import components as C
from app.ui import state


def _sys() -> SystemManager:
    s = state.svc()
    if s.system is None:
        s.system = SystemManager(s.hosted, s.db)
    return s.system


@st.dialog("Confirm system action")
def confirm_dialog(op: dict) -> None:
    sm = _sys()
    if op["op"] == "terminate":
        d = sm.check_terminate(op["pid"])
        title = f"{'Force end' if op.get('force') else 'End'} process {op['name']} (PID {op['pid']})"
    else:
        d = sm.check_power(op["action"])
        title = POWER_LABELS[op["action"]]
    st.markdown(f"**{title}**  \n{C.risk_badge(d.risk)}", unsafe_allow_html=True)
    st.markdown(C.callout("warn" if d.allowed else "bad", d.reason), unsafe_allow_html=True)
    ack = st.checkbox("I understand and want to continue", key="sys_ack") if d.risk == "HIGH" else True
    c1, c2 = st.columns(2)
    if c1.button("Confirm", type="primary", width="stretch", disabled=not (d.allowed and ack)):
        ok, msg = (sm.terminate(op["pid"], bool(op.get("force"))) if op["op"] == "terminate" else sm.power(op["action"]))
        state.push_event("OK" if ok else "ERR", f"System: {msg}")
        st.session_state.sys_result = (ok, msg)
        st.session_state.voice_say = msg
        st.rerun()
    if c2.button("Cancel", width="stretch"):
        state.push_event("WARN", f"System action cancelled: {title}")
        st.session_state.sys_result = (False, "Cancelled — nothing was changed.")
        st.rerun()


def _fmt_bat(b: dict | None) -> tuple[float | None, str]:
    if not b:
        return None, "no battery"
    return b["percent"], ("plugged in" if b["plugged"] else (b["left"] or "on battery"))


@st.fragment(run_every=2.5)
def live_panel() -> None:
    s, sm = state.svc(), _sys()
    m = s.monitor.sample(s.workspace)
    if not m.get("ok"):
        st.markdown(C.callout("warn", "Install psutil for live metrics."), unsafe_allow_html=True)
        return
    bp, bsub = _fmt_bat(sm.battery())
    g = (C.gauge("CPU", m["cpu"], f"{m['cores']} threads") + C.gauge("RAM", m["mem"], C.human_bytes(m["mem_used"]))
         + C.gauge("DISK", m["disk"], C.human_bytes(m["disk_total"] - m["disk_used"]) + " free")
         + C.gauge("BATT", bp, bsub))
    load = max(m["cpu"], m["mem"])
    score = max(0, round(100 - max(0, m["cpu"] - 50) * .6 - max(0, m["mem"] - 60) * .8 - max(0, m["disk"] - 75) * 1.2))
    status = (f"Health score {score}/100 · uptime {sm.uptime_text()} · {m['procs']} processes",
              "" if load < 80 else "amber")
    c1, c2 = st.columns([1.15, 1])
    c1.markdown(C.panel("System health", "cpu", f"<div class='gauges'>{g}</div>" + C.status_line(*status),
                        meta="cloud container" if s.hosted else "this PC"), unsafe_allow_html=True)
    cores = sm.per_core()
    bars = "".join(C.task_bar(f"Core {i}", v, f"{v:.0f}%") for i, v in enumerate(cores[:16]))
    charts = (C.area_chart("CPU usage", list(s.monitor.cpu), f"{m['cpu']:.0f}%", "#22d3ee", 100)
              + C.area_chart("Memory usage", list(s.monitor.mem), f"{m['mem']:.0f}%", "#34d399", 100)
              + C.area_chart("Network", list(s.monitor.net), f"{m['net_kbs']:.0f} KB/s", "#a78bfa"))
    c2.markdown(C.panel("Live resources", "chart", charts), unsafe_allow_html=True)
    if bars:
        st.markdown(C.panel("Per-core load", "cpu", f"<div class='core-grid'>{bars}</div>",
                            meta=f"{len(cores)} logical cores"), unsafe_allow_html=True)


def processes_tab(sm: SystemManager) -> None:
    rows = sm.processes()
    if not rows:
        st.info("Process list unavailable.")
        return
    c1, c2, c3 = st.columns([2, 1, 1])
    q = c1.text_input("Search processes", placeholder="name or PID", key="proc_q")
    sort = c2.selectbox("Sort by", ["Memory", "CPU", "Name", "PID"], key="proc_sort")
    c3.metric("Running", len(rows))
    df = pd.DataFrame(rows)
    if q:
        df = df[df["name"].str.contains(q, case=False, regex=False) | df["pid"].astype(str).str.startswith(q)]
    col = {"Memory": "mem_mb", "CPU": "cpu", "Name": "name", "PID": "pid"}[sort]
    df = df.sort_values(col, ascending=col in {"name", "pid"})
    ev = st.dataframe(df, hide_index=True, width="stretch", height=380, on_select="rerun", selection_mode="single-row",
                      key="proc_table", column_config={
                          "pid": st.column_config.NumberColumn("PID", format="%d"),
                          "name": "Process", "cpu": st.column_config.ProgressColumn("CPU %", min_value=0, max_value=100,
                                                                                     format="%.1f"),
                          "mem_mb": st.column_config.NumberColumn("Memory (MB)", format="%.1f"),
                          "status": "Status", "user": "User", "started": "Started"})
    sel = ev.selection.rows if ev and ev.selection else []
    if not sel:
        st.caption("Select a row to manage that process. Protected Windows processes, other users' processes and "
                   "the agent itself can never be ended.")
        return
    r = df.iloc[sel[0]]
    d = sm.check_terminate(int(r["pid"]))
    st.markdown(f"**{r['name']}** · PID {int(r['pid'])} · {r['mem_mb']:.0f} MB &nbsp; {C.risk_badge(d.risk)}",
                unsafe_allow_html=True)
    st.caption(d.reason)
    b1, b2, _ = st.columns([1, 1, 2])
    if b1.button("End process", icon=":material/cancel:", disabled=not d.allowed, width="stretch"):
        confirm_dialog({"op": "terminate", "pid": int(r["pid"]), "name": r["name"]})
    if b2.button("Force end", icon=":material/dangerous:", disabled=not d.allowed, width="stretch"):
        confirm_dialog({"op": "terminate", "pid": int(r["pid"]), "name": r["name"], "force": True})


def storage_tab(sm: SystemManager) -> None:
    parts = sm.partitions()
    if parts:
        st.markdown("".join(C.task_bar(f"{p['drive']}  ({p['fs']}) — {p['free']} free of {p['total']}",
                                       p["used_pct"], f"{p['used_pct']:.0f}% used") for p in parts),
                    unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(parts), hide_index=True, width="stretch")
    if st.button("Scan temporary files", icon=":material/cleaning_services:"):
        with st.spinner("Measuring the temp folder…"):
            st.session_state.temp_scan = sm.temp_usage()
    if t := st.session_state.get("temp_scan"):
        st.markdown(C.callout("info", f"<b>Temp folder</b> {t['path']} holds <b>{t['size']}</b> in {t['files']} "
                                      "file(s). Clean it with Windows Settings → Storage (Storage Sense); the agent "
                                      "never deletes outside approved folders."), unsafe_allow_html=True)


def network_tab(sm: SystemManager) -> None:
    n = sm.network()
    if n["interfaces"]:
        st.dataframe(pd.DataFrame(n["interfaces"]), hide_index=True, width="stretch")
    if n["connections"]:
        st.markdown(" ".join(C.chip(f"{k}: {v}") for k, v in sorted(n["connections"].items())), unsafe_allow_html=True)


@st.cache_data(ttl=60, show_spinner="Reading Windows services…")
def _services_cached(_sm: SystemManager) -> list[dict]:
    return _sm.services()


def services_tab(sm: SystemManager) -> None:
    rows = _services_cached(sm)
    if not rows:
        st.caption("Windows services are listed only when the agent runs locally on Windows.")
    else:
        df = pd.DataFrame(rows)
        c1, c2 = st.columns([2, 1])
        q = c1.text_input("Filter services", key="svc_q")
        flt = c2.selectbox("Status", ["all", "running", "stopped"], key="svc_st")
        if q:
            df = df[df["display_name"].str.contains(q, case=False, regex=False) |
                    df["name"].str.contains(q, case=False, regex=False)]
        if flt != "all":
            df = df[df["status"] == flt]
        st.dataframe(df, hide_index=True, width="stretch", height=300)
        st.caption("Read-only: changing services needs administrator rights, which the agent never requests.")
    st.markdown("**Startup programs**")
    items = sm.startup_items()
    if items:
        st.dataframe(pd.DataFrame(items), hide_index=True, width="stretch")
        st.caption("Read-only view. Disable startup apps in Task Manager → Startup apps.")
    else:
        st.caption("No startup items found (or not running on Windows).")


def controls_tab(sm: SystemManager) -> None:
    ok = sm.can_control
    if not ok:
        st.markdown(C.callout("info", f"<b>Read-only here.</b> {sm.control_reason()}"), unsafe_allow_html=True)
    st.markdown("**Media & volume**")
    cols = st.columns(len(MEDIA_KEYS))
    icons = [":material/volume_up:", ":material/volume_down:", ":material/volume_off:", ":material/play_pause:",
             ":material/skip_next:", ":material/skip_previous:"]
    for col, (name, ic) in zip(cols, zip(MEDIA_KEYS, icons)):
        if col.button(name.title(), icon=ic, key=f"mk_{name}", disabled=not ok, width="stretch"):
            res = sm.media_key(name, 5 if name.startswith("volume") else 1)
            st.session_state.sys_result = res
    st.markdown("**Windows Settings**")
    pages = sorted(SETTINGS_PAGES)
    for i in range(0, len(pages), 6):
        cols = st.columns(6)
        for col, p in zip(cols, pages[i:i + 6]):
            if col.button(p.title(), key=f"set_{p}", disabled=not ok, width="stretch"):
                st.session_state.sys_result = sm.open_settings(p)
    st.markdown("**Power**")
    cols = st.columns(4)
    for col, (a, ic) in zip(cols, [("lock", ":material/lock:"), ("restart", ":material/restart_alt:"),
                                   ("shutdown", ":material/power_settings_new:"), ("cancel", ":material/block:")]):
        if col.button(POWER_LABELS[a], icon=ic, key=f"pw_{a}", disabled=not ok, width="stretch",
                      type="primary" if a == "cancel" else "secondary"):
            if a == "cancel":
                st.session_state.sys_result = sm.power("cancel")
            else:
                confirm_dialog({"op": "power", "action": a})


def render() -> None:
    s, sm = state.svc(), _sys()
    st.markdown(C.page_title("System Manager", "Health · processes · storage · network · services · controls",
                             "cpu"), unsafe_allow_html=True)
    if s.hosted:
        st.markdown(C.callout("info", "<b>Cloud website:</b> these are the live stats of the cloud container running "
                                      "this app. Run the agent locally (run.bat) to manage your own PC — process, "
                                      "volume, settings and power controls unlock there."), unsafe_allow_html=True)
    if res := st.session_state.pop("sys_result", None):
        (st.success if res[0] else st.warning)(res[1])
    live_panel()
    tabs = st.tabs([":material/memory: Processes", ":material/storage: Storage", ":material/lan: Network",
                    ":material/settings_applications: Services & startup", ":material/tune: Controls",
                    ":material/info: System info"])
    with tabs[0]:
        processes_tab(sm)
    with tabs[1]:
        storage_tab(sm)
    with tabs[2]:
        network_tab(sm)
    with tabs[3]:
        services_tab(sm)
    with tabs[4]:
        controls_tab(sm)
    with tabs[5]:
        st.dataframe(pd.DataFrame(sm.info().items(), columns=["Property", "Value"]), hide_index=True, width="stretch")

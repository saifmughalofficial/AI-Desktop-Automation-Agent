"""Apps & Automation: allowlisted apps, UI inspector and saved workflows."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.actions import app_launcher, ui_automation
from app.config.settings import Workflow
from app.ui import components as C
from app.ui import state


def _go(cmd: str, auto: str = "preview") -> None:
    state.queue_command(cmd, auto)
    st.switch_page(st.session_state.pages["command"])


def render() -> None:
    s = state.svc()
    st.markdown(C.page_title("Apps & Automation", "Allowlisted applications · accessibility inspector · workflows",
                             "app"), unsafe_allow_html=True)
    ok, msg = ui_automation.available()
    if s.hosted:
        st.markdown(C.callout("info", "<b>Cloud sandbox:</b> a website cannot control your PC, so apps open as working "
                                      "<b>web windows</b> in the Command Center's virtual desktop (Notepad, Calculator, "
                                      "Paint, Character Map). Run the agent locally on Windows (run.bat) to control the "
                                      "real apps."), unsafe_allow_html=True)
    else:
        st.markdown(C.callout("ok" if ok else "warn", f"<b>UI automation:</b> {msg}"), unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["Applications", "UI inspector", "Workflows"])
    with tab1:
        cols = st.columns(3)
        for i, app in enumerate(s.settings.apps):
            exe = app_launcher.resolve_command(app) if not s.hosted else None
            status = "web app" if s.hosted else ("installed" if exe else "not found")
            with cols[i % 3]:
                st.markdown(f"<div class='appcard'>{C.icon('app', 'big')}<div class='nm'>{app.name}</div>"
                            f"<div class='cmd'>{app.command} · {status}"
                            f"{' · automatable' if app.automatable else ''}</div></div>", unsafe_allow_html=True)
                if st.button(f"Launch {app.name}", key=f"launch_{app.name}", width="stretch",
                             icon=":material/rocket_launch:", disabled=not (s.hosted or exe)):
                    _go(f"open {app.name}", "run")
        st.caption("Only these programs can be launched. Shells, script hosts and system tools are blocked. "
                   "Manage the list in Settings → Applications.")

    with tab2:
        st.write("Read-only view of an app window's accessibility tree (Windows UI Automation). "
                 "The agent locates controls this way instead of using screen coordinates.")
        names = [a.name for a in s.settings.apps]
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        target = c1.selectbox("Application window", names)
        if c2.button("Inspect", type="primary", width="stretch", disabled=not (s.hosted or ok)):
            app = s.perms.find_app(target)
            if s.hosted:
                st.session_state.pop("inspect_rows", None)
                _go(f"inspect the {app.name} window", "run")
            handle = (s.orchestrator.launched.get(app.name.lower()) or {}).get("handle")
            try:
                rows = ui_automation.inspect_window(app.window_title, handle)
                st.session_state.inspect_rows = (app.name, rows)
                state.push_event("OK", f"Inspected {len(rows)} controls in {app.name}")
            except Exception as exc:
                st.session_state.inspect_rows = None
                st.markdown(C.callout("warn", f"<b>Could not inspect {target}:</b> {exc}"), unsafe_allow_html=True)
        data = st.session_state.get("inspect_rows")
        if data:
            st.caption(f"{data[0]} — {len(data[1])} controls")
            st.dataframe(pd.DataFrame(data[1]), hide_index=True, width="stretch", height=420)

    with tab3:
        for i, wf in enumerate(s.settings.workflows):
            with st.container(border=True):
                c1, c2, c3 = st.columns([5, 1.2, 1])
                c1.markdown(f"**{wf.name}** — {wf.description}")
                c1.code("\n".join(wf.commands), language=None)
                if c2.button("Run", key=f"wf_run_{i}", type="primary", icon=":material/play_arrow:", width="stretch"):
                    _go(f"run workflow {wf.name}", "preview")
                if c3.button("Delete", key=f"wf_del_{i}", icon=":material/delete:", width="stretch"):
                    new = s.settings.model_copy(deep=True)
                    new.workflows.pop(i)
                    s.apply_settings(new)
                    st.rerun()
        with st.form("new_wf", clear_on_submit=True):
            st.markdown("**Create a workflow** — one supported command per line. Each step still goes through "
                        "the planner, the policy engine and approval.")
            name = st.text_input("Name", placeholder="Morning setup")
            desc = st.text_input("Description", placeholder="Open my tools and check Downloads")
            cmds = st.text_area("Commands", placeholder="open notepad\nlist the files in Downloads")
            if st.form_submit_button("Save workflow", type="primary"):
                lines = [c.strip() for c in cmds.splitlines() if c.strip()]
                try:
                    wf = Workflow(name=name.strip(), description=desc.strip(), commands=lines)
                    if any(w.name.lower() == wf.name.lower() for w in s.settings.workflows):
                        raise ValueError("a workflow with that name already exists")
                    blocked = [c for c in lines if s.policy.screen_request(c)]
                    if blocked:
                        raise ValueError(f"refused by policy: {blocked[0]}")
                    new = s.settings.model_copy(deep=True)
                    new.workflows.append(wf)
                    s.apply_settings(new)
                    st.success(f"Workflow '{wf.name}' saved.")
                    st.rerun()
                except ValueError as exc:
                    st.error(f"Could not save: {exc}")

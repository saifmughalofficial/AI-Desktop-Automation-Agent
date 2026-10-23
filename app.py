"""AI Desktop Automation Agent — Streamlit entry point.

Local:  run.bat  (or: streamlit run app.py --server.port 8797)
Cloud:  main file path = app.py on share.streamlit.io
"""
from __future__ import annotations

import streamlit as st

from app import __version__
from app.ui import (automation_page, explorer_page, history_page, main_window, manual_page, settings_dialog, state,
                    system_page, voice_hud, voice_page, web_voice)
from app.ui.components import icon
from app.ui.theme import CSS, FX_CSS, PALETTES, STATIC_CSS, fx_script

st.set_page_config(page_title="AI Desktop Automation Agent", page_icon="🛡️", layout="wide",
                   initial_sidebar_state="expanded")

s = state.svc()
st.html(f"<style>{CSS}{FX_CSS}{PALETTES.get(s.settings.theme, PALETTES['dual'])}"
        f"{'' if s.settings.animations else STATIC_CSS}</style>")
st.html(fx_script(s.settings.theme == "dual", s.settings.animations, s.settings.background_fx,
                  len(s.settings.approved_roots), len(s.settings.apps)), unsafe_allow_javascript=True)


def sidebar() -> None:
    with st.sidebar:
        st.html(f"""<div class="side-brand"><svg viewBox="0 0 48 48"><defs><linearGradient id="lg" x1="0" x2="1">
<stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#3b82f6"/></linearGradient></defs>
<path d="M24 3l17 8v12c0 11-7.5 18.5-17 22C14.5 41.5 7 34 7 23V11z" fill="none" stroke="url(#lg)" stroke-width="2.5"/>
<circle cx="24" cy="22" r="6" fill="none" stroke="#22d3ee" stroke-width="2"/><path d="M24 10v6M24 28v6M12 22h6M30 22h6" stroke="#38bdf8" stroke-width="2"/></svg>
<div><b>AI DESKTOP<br>AUTOMATION AGENT</b><span>v{__version__} · {'HOSTED SANDBOX' if s.hosted else 'LOCAL'}</span></div></div>""")
        run = state.get_run()
        if run and not run.done:
            st.markdown('<div class="stop-btn">', unsafe_allow_html=True)
            if st.button("EMERGENCY STOP", icon=":material/dangerous:", width="stretch", key="side_stop",
                         shortcut="Ctrl+Shift+X", help="Shortcut: Ctrl+Shift+X"):
                s.orchestrator.stop(run)
                state.push_event("WARN", f"Run {run.id}: STOP pressed (sidebar).")
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            st.caption(f"Run {run.id}: {run.status} · {run.progress * 100:.0f}%")
        stats = s.db.stats()
        rows = [("Engine", main_window.engine_label(s).title()), ("Approved folders", len(s.settings.approved_roots)),
                ("Allowlisted apps", len(s.settings.apps)), ("Tasks recorded", stats["tasks"]),
                ("Selection", f"{len(state.selection())} file(s)")]
        st.html("".join(f"<div class='side-stat'><span>{k}</span><b>{v}</b></div>" for k, v in rows))
        voice_hud.sidebar_indicator()
        st.caption("Offline-capable · no paid APIs · every action policy-checked")


pages = {
    "command": st.Page(main_window.render, title="Command Center", icon=":material/dashboard:", default=True),
    "files": st.Page(explorer_page.render, title="File Explorer", icon=":material/folder_open:", url_path="files"),
    "apps": st.Page(automation_page.render, title="Apps & Automation", icon=":material/smart_toy:", url_path="apps"),
    "system": st.Page(system_page.render, title="System Manager", icon=":material/monitor_heart:", url_path="system"),
    "voice": st.Page(voice_page.render, title="Voice Assistant", icon=":material/mic:", url_path="voice"),
    "history": st.Page(history_page.render, title="Activity & History", icon=":material/history:", url_path="history"),
    "settings": st.Page(settings_dialog.render, title="Settings", icon=":material/tune:", url_path="settings"),
    "manual": st.Page(manual_page.render, title="Manual", icon=":material/menu_book:", url_path="manual"),
}
st.session_state.pages = pages
nav = st.navigation({"Agent": [pages["command"], pages["files"], pages["apps"]],
                     "System": [pages["system"], pages["voice"]],
                     "Records & setup": [pages["history"], pages["settings"], pages["manual"]]})
voice_hud.ensure()
web_voice.mount()
sidebar()
nav.run()
voice_page.play_pending()

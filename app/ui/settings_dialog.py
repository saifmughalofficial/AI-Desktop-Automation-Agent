"""Settings: approved folders, application allowlist, local AI, safety policy and workspace."""
from __future__ import annotations

import streamlit as st

from app.actions.app_launcher import validate_app_command
from app.config.settings import AppEntry, ApprovedRoot
from app.core.permissions import PathViolation, check_root_candidate
from app.demo_seed import reset_demo_workspace
from app.llm.local_model import LocalModelClient, check_local_url
from app.runtime import DEMO_WORKSPACE
from app.ui import components as C
from app.ui import state


def _save(new, msg: str) -> None:
    state.svc().apply_settings(new)
    state.push_event("INFO", msg)
    st.toast(msg, icon=":material/check_circle:")
    st.rerun()


def render() -> None:
    s = state.svc()
    st.markdown(C.page_title("Settings", "Permissions · applications · local AI · safety policy", "settings"),
                unsafe_allow_html=True)
    if s.hosted:
        st.markdown(C.callout("info", "<b>Hosted sandbox:</b> settings apply to this browser session only, and only "
                                      "the sandbox demo folder can be approved."), unsafe_allow_html=True)
    t1, t2, t3, t4, t5 = st.tabs(["Approved folders", "Applications", "Local AI", "Safety & execution", "Workspace"])

    # ------------------------------------------------------------------ folders
    with t1:
        st.write("The agent can only touch files inside these folders. Paths are canonicalised, so symlinks, "
                 "junctions and `..` cannot escape them.")
        for i, r in enumerate(s.settings.approved_roots):
            c1, c2, c3, c4 = st.columns([1.2, 4, 1.3, 1], vertical_alignment="center")
            c1.markdown(f"**{r.alias}**")
            c2.code(r.path, language=None)
            access = c3.selectbox("Access", ["read_write", "read"], index=0 if r.access == "read_write" else 1,
                                  key=f"acc_{i}", label_visibility="collapsed")
            if access != r.access:
                new = s.settings.model_copy(deep=True)
                new.approved_roots[i].access = access
                _save(new, f"'{r.alias}' access set to {access}.")
            if c4.button("Remove", key=f"rm_root_{i}", width="stretch"):
                new = s.settings.model_copy(deep=True)
                new.approved_roots.pop(i)
                _save(new, f"Removed approved folder '{r.alias}'.")
        with st.form("add_root", clear_on_submit=True):
            st.markdown("**Approve a folder**")
            c1, c2, c3 = st.columns([1.2, 4, 1.4])
            alias = c1.text_input("Alias", placeholder="Downloads")
            path = c2.text_input("Full folder path", placeholder=r"C:\Users\you\Downloads", disabled=s.hosted)
            acc = c3.selectbox("Access", ["read_write", "read"])
            if st.form_submit_button("Add folder", type="primary", disabled=s.hosted):
                try:
                    real = check_root_candidate(path)
                    root = ApprovedRoot(alias=alias or real.name, path=str(real), access=acc)
                    if root.alias.lower() in {a.lower() for a in s.settings.root_aliases()}:
                        raise ValueError("that alias is already used")
                    new = s.settings.model_copy(deep=True)
                    new.approved_roots.append(root)
                    _save(new, f"Approved '{root.alias}' → {real}")
                except (PathViolation, ValueError) as exc:
                    st.error(f"Not added: {exc}")

    # ------------------------------------------------------------------ apps
    with t2:
        st.write("Only allowlisted programs can be launched. Shells, script hosts and system tools are refused.")
        for i, a in enumerate(s.settings.apps):
            c1, c2, c3, c4 = st.columns([1.5, 3, 1.4, 1], vertical_alignment="center")
            c1.markdown(f"**{a.name}**")
            c2.code(a.command + (f"   aliases: {', '.join(a.aliases)}" if a.aliases else ""), language=None)
            c3.markdown("automation ✓" if a.automatable else "launch only")
            if c4.button("Remove", key=f"rm_app_{i}", width="stretch"):
                new = s.settings.model_copy(deep=True)
                new.apps.pop(i)
                _save(new, f"Removed {a.name} from the allowlist.")
        with st.form("add_app", clear_on_submit=True):
            st.markdown("**Allowlist an application**")
            c1, c2 = st.columns([1.3, 3])
            name = c1.text_input("Display name", placeholder="VS Code")
            cmd = c2.text_input(".exe path or name on PATH", placeholder=r"C:\Program Files\App\app.exe")
            c3, c4 = st.columns([3, 1.3])
            aliases = c3.text_input("Aliases (comma separated)", placeholder="code, vscode")
            title = c4.text_input("Window title regex", placeholder=".* - App$")
            if st.form_submit_button("Add application", type="primary", disabled=s.hosted):
                try:
                    validate_app_command(cmd)
                    entry = AppEntry(name=name.strip() or cmd, command=cmd.strip(),
                                     aliases=[x.strip().lower() for x in aliases.split(",") if x.strip()],
                                     window_title=title.strip())
                    new = s.settings.model_copy(deep=True)
                    new.apps.append(entry)
                    _save(new, f"Allowlisted {entry.name}.")
                except ValueError as exc:
                    st.error(f"Not added: {exc}")

    # ------------------------------------------------------------------ local AI
    with t3:
        st.markdown(C.callout("info", "<b>100% local and optional.</b> The agent never calls cloud APIs and needs no "
                                      "API key. Without a model, the rules engine handles all supported commands. "
                                      "To add a model: install <b>Ollama</b> (ollama.com), then run "
                                      "<code>ollama pull llama3.2:3b</code> once — this one-time download needs "
                                      "internet; after that everything runs offline."), unsafe_allow_html=True)
        cfg = s.settings.llm
        with st.form("llm"):
            modes = ["auto", "rules", "ollama", "llamacpp"]
            mode = st.radio("Mode", modes, index=modes.index(cfg.mode), horizontal=True,
                            captions=["rules first, model for the rest", "never use a model", "Ollama only",
                                      "llama.cpp server only"])
            c1, c2 = st.columns(2)
            o_url = c1.text_input("Ollama URL", cfg.ollama_url)
            o_model = c2.text_input("Ollama model", cfg.ollama_model)
            c3, c4 = st.columns(2)
            l_url = c3.text_input("llama.cpp server URL", cfg.llamacpp_url)
            timeout = c4.slider("Timeout (seconds)", 5, 180, int(cfg.timeout_s))
            if st.form_submit_button("Save AI settings", type="primary"):
                try:
                    new = s.settings.model_copy(deep=True)
                    new.llm.mode, new.llm.ollama_model, new.llm.timeout_s = mode, o_model.strip(), timeout
                    new.llm.ollama_url, new.llm.llamacpp_url = check_local_url(o_url), check_local_url(l_url)
                    _save(new, f"Local AI mode: {mode}.")
                except ValueError as exc:
                    st.error(str(exc))
        if st.button("Test connection", icon=":material/network_check:"):
            client = LocalModelClient(s.settings.llm.model_copy(update={"mode": "auto" if cfg.mode == "rules" else cfg.mode}))
            res = client.status(max_age=0)
            (st.success if res and res.get("available") else st.warning)(res.get("detail", "No response"))
            if res and res.get("models"):
                st.caption("Models found: " + ", ".join(res["models"]))

    # ------------------------------------------------------------------ safety
    with t4:
        p, e = s.settings.policy, s.settings.execution
        with st.form("policy"):
            c1, c2 = st.columns(2)
            req = c1.toggle("Require approval for MEDIUM-risk plans", p.require_approval_medium,
                            help="HIGH-risk plans always require approval; this cannot be disabled.")
            jit = c1.toggle("Ask again right before each HIGH-risk step", p.jit_confirm_high)
            stop = c1.toggle("Stop the run when an action fails", p.stop_on_failure)
            conflict = c2.selectbox("When a file name already exists", ["ask", "skip", "rename"],
                                    index=["ask", "skip", "rename"].index(p.conflict_policy),
                                    format_func={"ask": "Pause and ask me", "skip": "Skip that item",
                                                 "rename": "Keep both (auto-rename)"}.get)
            max_a = c2.number_input("Max actions per run", 1, 500, p.max_actions_per_run)
            max_d = c2.number_input("Max deletes per run", 1, 100, p.max_bulk_delete)
            delay = st.slider("Pause between actions (s) — gives you time to press STOP", 0.0, 3.0,
                              float(e.step_delay_s), 0.05)
            vt = st.slider("Launch verification timeout (s)", 1, 30, int(e.verify_launch_timeout_s))
            if st.form_submit_button("Save safety settings", type="primary"):
                new = s.settings.model_copy(deep=True)
                new.policy.require_approval_medium, new.policy.jit_confirm_high = req, jit
                new.policy.stop_on_failure, new.policy.conflict_policy = stop, conflict
                new.policy.max_actions_per_run, new.policy.max_bulk_delete = int(max_a), int(max_d)
                new.execution.step_delay_s, new.execution.verify_launch_timeout_s = float(delay), float(vt)
                _save(new, "Safety settings saved.")
        st.caption("Never configurable: shell/script execution, credential access, security bypass, stealth "
                   "operation, system-setting changes, installs, messaging and uploads are always refused.")

    # ------------------------------------------------------------------ workspace
    with t5:
        c1, c2 = st.columns(2)
        with c1:
            hist = st.toggle("Record task history", s.settings.history_enabled)
            anim = st.toggle("HUD animations & live refresh", s.settings.animations)
            fx = st.toggle("Animated circuit-board background", s.settings.background_fx)
            theme = st.segmented_control("Color theme", ["dual", "blue"], default=s.settings.theme,
                                         format_func={"dual": "Dual Neon (blue × red)", "blue": "Cyber Blue"}.get)
            theme = theme or s.settings.theme
            opts = ["chrome", "edge", "firefox", "default"]
            web = st.selectbox("Browser for websites (when you don't name one)", opts,
                               index=opts.index(s.settings.web_browser),
                               format_func={"chrome": "Google Chrome (new tab)", "edge": "Microsoft Edge (new tab)",
                                            "firefox": "Mozilla Firefox (new tab)",
                                            "default": "Windows default browser"}.get)
            if (hist, anim, fx, theme, web) != (s.settings.history_enabled, s.settings.animations,
                                                s.settings.background_fx, s.settings.theme, s.settings.web_browser):
                new = s.settings.model_copy(deep=True)
                new.history_enabled, new.animations, new.background_fx, new.theme = hist, anim, fx, theme
                new.web_browser = web
                _save(new, "Workspace preferences saved.")
            st.caption(f"Data folder (settings, history, logs): `{s.data_dir}`")
            st.caption(f"Demo workspace: `{s.workspace}`")
        with c2:
            with st.popover("Reset demo workspace", icon=":material/restart_alt:", width="stretch"):
                st.write("Delete everything inside the demo workspace and recreate the sample files? "
                         "Only the demo folder is touched.")
                if st.button("Yes, reset demo files", type="primary"):
                    expected = s.workspace if s.hosted else DEMO_WORKSPACE
                    reset_demo_workspace(s.workspace, expected)
                    state.push_event("WARN", "Demo workspace reset to sample files.")
                    st.success("Demo workspace restored.")
            if st.button("Restore default settings", icon=":material/settings_backup_restore:", width="stretch"):
                from app.config.settings import load_defaults
                _save(load_defaults(s.workspace), "Default settings restored.")

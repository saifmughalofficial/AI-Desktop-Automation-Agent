"""Per-browser-session state: services, current plan/run, selection and the event feed."""
from __future__ import annotations

from collections import deque
from datetime import datetime

import streamlit as st

from app.core.action_schema import PathRef, Plan
from app.core.orchestrator import RunState
from app.services import Services, build_services


def svc() -> Services:
    if "svc" not in st.session_state:
        st.session_state.svc = build_services()
        push_event("INFO", "Agent services online · policy engine armed")
        push_event("INFO", f"Approved folders: {', '.join(st.session_state.svc.settings.root_aliases())}")
    return st.session_state.svc


def events() -> deque:
    if "events" not in st.session_state:
        st.session_state.events = deque(maxlen=200)
    return st.session_state.events


def push_event(level: str, msg: str) -> None:
    events().append((datetime.now().strftime("%H:%M:%S"), level, msg))


def get_plan() -> Plan | None:
    return st.session_state.get("plan")


def set_plan(plan: Plan | None) -> None:
    st.session_state.plan = plan


def get_run() -> RunState | None:
    return st.session_state.get("run")


def set_run(run: RunState | None) -> None:
    st.session_state.run = run


def selection() -> list[PathRef]:
    return st.session_state.setdefault("selection", [])


def context_folder() -> PathRef | None:
    return st.session_state.get("context_folder")


def queue_command(text: str, auto: str | None = None) -> None:
    """Put a command into the Command Center input; auto='preview'|'run' plans it immediately."""
    st.session_state.cmd_input = text
    st.session_state.auto_cmd = auto


def run_is_active() -> bool:
    run = get_run()
    return bool(run and run.status in {"running", "queued", "paused"})


def make_plan(text: str) -> Plan:
    s = svc()
    plan = s.planner.plan(text, selection=selection(), current=context_folder())
    set_plan(plan)
    if plan.blocked_reason:
        push_event("FAIL", f"Refused: {plan.blocked_reason}")
        s.orchestrator.record_refusal(text, plan.blocked_reason)
    elif plan.clarification:
        push_event("WARN", f"Clarification needed: {plan.clarification}")
    elif plan.help:
        push_event("INFO", "Help requested")
    else:
        push_event("INFO", f"Plan ready ({plan.engine}): {plan.summary} · risk {plan.risk.value}")
    return plan

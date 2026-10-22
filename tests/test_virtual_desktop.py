"""Hosted mode: app actions run in the web virtual desktop with verification."""
from app.core.action_schema import StepStatus


def run(svc, text):
    p = svc.planner.plan(text)
    assert p.executable, (p.clarification, p.violations)
    return svc.orchestrator.submit(p, approved=True, background=False)


def test_open_notepad_and_type_in_cloud(svc):
    st = run(svc, "type 'Hello cloud' in Notepad")
    assert st.status == "completed" and all(s.verified for s in st.steps)
    win = svc.orchestrator.virtual.latest("notepad")
    assert win and "Hello cloud" in win["text"]


def test_calculator_paint_inspect_and_open_file(svc):
    for cmd in ["open calculator", "open paint", "open notepad then inspect the Notepad window", "open roadmap.txt",
                "open the Photos folder"]:
        st = run(svc, cmd)
        assert st.status == "completed", (cmd, [s.message for s in st.steps])
    kinds = {w["kind"] for w in svc.orchestrator.virtual.windows.values()}
    assert {"calculator", "paint", "notepad", "viewer", "explorer"} <= kinds


def test_typing_requires_window_opened_by_agent(svc):
    from app.core import action_schema as A
    from app.core.action_schema import Plan, PlanStep
    p = svc.policy.evaluate(Plan(request="t", steps=[PlanStep(index=0, action=A.TypeText(app="Notepad", text="x"), description="x")]))
    st = svc.orchestrator.submit(p, approved=True, background=False)
    assert st.steps[0].status == StepStatus.FAILED

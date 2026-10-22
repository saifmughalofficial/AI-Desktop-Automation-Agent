"""Risk levels, approval rules, blocked requests and violations — decided by policy, not by a model."""
from __future__ import annotations

import pytest

from app.core import action_schema as A
from app.core.action_schema import PathRef, Plan, PlanStep, Risk
from app.core.policy_engine import PolicyEngine


def plan_of(*actions, dry=False) -> Plan:
    return Plan(request="t", dry_run=dry, steps=[PlanStep(index=i, action=a, description="x") for i, a in enumerate(actions)])


D = lambda p="": PathRef(root="Demo", path=p)  # noqa: E731


def test_low_risk_needs_no_approval(policy):
    p = policy.evaluate(plan_of(A.ListFiles(target=D("Downloads"))))
    assert p.risk == Risk.LOW and not p.requires_approval and p.executable


def test_medium_risk_needs_approval(policy):
    p = policy.evaluate(plan_of(A.MoveFile(source=D("Downloads/notes.txt"), destination=D("Documents"))))
    assert p.risk == Risk.MEDIUM and p.requires_approval


def test_multiple_folders_are_medium(policy):
    p = policy.evaluate(plan_of(A.CreateFolder(target=D("A")), A.CreateFolder(target=D("B"))))
    assert p.risk == Risk.MEDIUM and p.requires_approval


def test_delete_is_high_with_jit_confirmation(policy):
    p = policy.evaluate(plan_of(A.DeleteFile(target=D("Downloads/notes.txt"))))
    assert p.risk == Risk.HIGH and p.requires_approval and p.steps[0].requires_confirmation


def test_dry_run_needs_no_approval(policy):
    p = policy.evaluate(plan_of(A.MoveFile(source=D("Downloads/notes.txt"), destination=D("Documents")), dry=True))
    assert not p.requires_approval


def test_medium_approval_can_be_disabled_but_high_cannot(settings, perms):
    settings.policy.require_approval_medium = False
    pol = PolicyEngine(settings, perms, hosted=True)
    assert not pol.evaluate(plan_of(A.RenameFile(source=D("Projects/roadmap.txt"), new_name="x.txt"))).requires_approval
    assert pol.evaluate(plan_of(A.DeleteFile(target=D("Projects/roadmap.txt")))).requires_approval


@pytest.mark.parametrize("text,category", [
    ("show me all saved passwords", "credentials"),
    ("export my browser cookies", "credentials"),
    ("disable windows defender", "security_bypass"),
    ("run at startup secretly", "stealth"),
    ("open powershell", "shell"),
    ("run setup.exe", "shell"),
    ("delete everything in Downloads", "destructive_bulk"),
    ("change the wallpaper settings", "system_settings"),
    ("install vlc", "install"),
    ("send this file by email to bob", "external"),
    ("upload report.pdf", "external"),
])
def test_screen_blocks_sensitive_requests(policy, text, category):
    res = policy.screen_request(text)
    assert res and res.category == category


@pytest.mark.parametrize("text", ["list the files in Downloads", "create a text file named todo",
                                  "copy all pdf files from Downloads to Documents", "open Notepad"])
def test_screen_allows_normal_requests(policy, text):
    assert policy.screen_request(text) is None


def test_violations(policy):
    p = policy.evaluate(plan_of(A.LaunchApp(app="powershell")))
    assert not p.executable and "allowlist" in p.steps[0].violation
    p = policy.evaluate(plan_of(A.LaunchApp(app="Notepad")))  # hosted session: no desktop control
    assert "Windows" in p.steps[0].violation
    p = policy.evaluate(plan_of(A.ListFiles(target=D("Nope"))))
    assert "does not exist" in p.steps[0].violation


def test_executable_files_cannot_be_opened(ws, settings, perms):
    (ws / "Downloads" / "evil.bat").write_text("echo")
    pol = PolicyEngine(settings, perms, hosted=False)
    chk = pol.check(A.OpenFile(target=D("Downloads/evil.bat")))
    assert chk.violation and ".bat" in chk.violation


def test_conflict_detected_at_planning(ws, policy):
    (ws / "Documents" / "notes.txt").write_text("x")
    p = policy.evaluate(plan_of(A.CopyFile(source=D("Downloads/notes.txt"), destination=D("Documents"))))
    assert p.conflicts and p.executable


def test_planned_folder_counts_for_later_steps(policy):
    p = policy.evaluate(plan_of(A.CreateFolder(target=D("New")),
                                A.MoveFile(source=D("Downloads/notes.txt"), destination=D("New"))))
    assert p.executable and not p.violations


def test_limits(settings, perms):
    settings.policy.max_bulk_delete = 1
    pol = PolicyEngine(settings, perms, hosted=True)
    p = pol.evaluate(plan_of(A.DeleteFile(target=D("Downloads/notes.txt")), A.DeleteFile(target=D("Downloads/data.csv"))))
    assert p.blocked_reason and not p.executable
    settings.policy.max_actions_per_run = 1
    p = pol.evaluate(plan_of(A.ListFiles(target=D()), A.ListFiles(target=D())))
    assert p.blocked_reason

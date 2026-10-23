"""Policy engine: the single authority on risk, approval and what is allowed.

A planner (rules or local model) only *proposes* actions. This module decides
the risk level, whether approval / just-in-time confirmation is required, and
rejects anything outside the approved folders or the application allowlist.
A model's opinion about risk is never consulted."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.config.settings import Settings
from app.core import action_schema as A
from app.core.action_schema import Plan, Risk, max_risk
from app.core.permissions import PathViolation, Permissions
from app.actions.virtual_desktop import WEB_APPS
from app.runtime import IS_WINDOWS

BASE_RISK: dict[str, Risk] = {
    "list_files": Risk.LOW, "find_duplicates": Risk.LOW, "create_folder": Risk.LOW,
    "launch_app": Risk.LOW, "open_file": Risk.LOW, "open_folder": Risk.LOW, "inspect_ui": Risk.LOW,
    "copy_file": Risk.MEDIUM, "move_file": Risk.MEDIUM, "rename_file": Risk.MEDIUM,
    "write_text_file": Risk.MEDIUM, "archive_folder": Risk.MEDIUM, "type_text": Risk.MEDIUM,
    "delete_file": Risk.HIGH,
    "open_url": Risk.LOW, "list_windows": Risk.LOW, "window_control": Risk.LOW, "browser_tab": Risk.LOW,
    "compose_message": Risk.MEDIUM, "launch_program": Risk.MEDIUM, "take_screenshot": Risk.MEDIUM,
}

EXECUTABLE_EXTS = {
    "exe", "bat", "cmd", "com", "ps1", "psm1", "psd1", "vbs", "vbe", "js", "jse", "wsf", "wsh", "msi", "msp",
    "scr", "lnk", "reg", "hta", "cpl", "jar", "py", "pyw", "sh", "appref-ms", "url", "inf", "dll", "sys",
    "application", "gadget", "msc", "pif", "scf", "website",
}
TEXT_WRITE_EXTS = {"txt", "md", "csv", "json", "log"}


@dataclass
class ScreenResult:
    category: str
    risk: Risk
    message: str


# Requests in these categories never reach the planner. HIGH = a legitimate but
# high-risk category this version deliberately does not implement; BLOCKED = never.
_SCREEN_RULES: list[tuple[str, Risk, re.Pattern, str]] = [
    ("credentials", Risk.BLOCKED,
     re.compile(r"\b(passwords?|passwd|credentials?|cookies?|session tokens?|api keys?|private keys?|keylog\w*|"
                r"steal\w*|harvest\w*|crack(ing)?|dump (the )?(hashes|sam|lsass))\b", re.I),
     "Accessing, collecting or exporting passwords, cookies, tokens or other secrets is blocked."),
    ("account_access", Risk.BLOCKED,
     re.compile(r"\b(sign|log)\s?(me\s)?(in|into|on)\b.{0,50}\b(account|facebook|instagram|whatsapp|gmail|google|"
                r"twitter|linkedin|tiktok|snapchat|telegram|outlook|bank|amazon|netflix|for me|with my|as me)\b|"
                r"\b(enter|type|fill in|use) (my |the )?(password|login|credentials|otp|2fa|pin)\b", re.I),
     "The agent never signs in to accounts or enters passwords for you. Say e.g. 'open facebook.com' and sign in "
     "yourself — the agent can then help with drafts, tabs and windows."),
    ("security_bypass", Risk.BLOCKED,
     re.compile(r"\b(disable|turn off|bypass|kill|stop|evade)\b.{0,40}\b(antivirus|defender|firewall|uac|"
                r"smartscreen|security|edr)\b|\b(exploit|privilege escalation|backdoor|rootkit|ransomware|malware)\b", re.I),
     "Disabling, bypassing or evading security controls is blocked."),
    ("stealth", Risk.BLOCKED,
     re.compile(r"\b(stealth\w*|secretly|covertly|without (the user|anyone|me|them|him|her) (knowing|noticing)|"
                r"persistence|autorun|(run|start) (at|on) (startup|boot|login)|startup folder|"
                r"hide (the |its |your)?(window|process|yourself|itself|activity))\b", re.I),
     "Hidden, persistent or stealth operation is blocked — the agent always works visibly."),
    ("shell", Risk.BLOCKED,
     re.compile(r"\b(powershell|pwsh|cmd(\.exe)?|command prompt|bash|shell command|regsvr32|rundll32|mshta|"
                r"(execute|run) (a |the |this |my )?(script|command|code|program|binary)|eval|exec)\b|"
                r"\b(run|execute|start|open|launch)\s+[^\s/]+\.(exe|bat|cmd|ps1|vbs|msi|scr|py|js|jar)\b", re.I),
     "Running arbitrary commands, scripts or executables is not allowed. Only registered actions and "
     "allowlisted applications can run."),
    ("destructive_bulk", Risk.BLOCKED,
     re.compile(r"\b(format|wipe|erase|delete|remove|destroy)\b.{0,30}\b(drive|disk|partition|c:|everything|"
                r"all (of )?(my |the )?files|whole|entire|all folders)\b", re.I),
     "Destructive bulk actions on whole folders or drives are blocked. Select specific files to delete instead."),
    ("system_settings", Risk.HIGH,
     re.compile(r"\b(registry|regedit|group policy|system settings?|control panel|bios|bcdedit|"
                r"change (the |my )?(wallpaper|system|network|display|power|security|privacy) settings?|"
                r"(create|add|delete) (a )?(user|account)|scheduled task)\b", re.I),
     "Changing system settings is a high-risk action that this version does not perform."),
    ("install", Risk.HIGH,
     re.compile(r"\b(install|uninstall|reinstall|setup\.exe|download and (run|install))\b", re.I),
     "Installing or removing software is a high-risk action that this version does not perform."),
    ("external", Risk.HIGH,
     re.compile(r"\b(send|forward)\b.{0,40}\b(email|e-mail|mail|message|sms|text|dm|whatsapp)\b|"
                r"\b(email|e-mail|mail) (it|this|them|the|my)\b|\b(upload|tweet|publish|purchase|buy|pay for|"
                r"checkout)\b|\bshare\b.{0,30}\b(with|online|on|link)\b|"
                r"\bpost\b.{0,25}\b(facebook|twitter|linkedin|instagram|reddit|slack|teams|discord)\b", re.I),
     "The agent never sends, posts, uploads or buys on your behalf. Say 'draft an email to …' or 'draft a "
     "WhatsApp message …' and it opens a pre-filled draft that you review and send yourself."),
]


@dataclass
class StepCheck:
    risk: Risk
    targets: list[str] = field(default_factory=list)
    violation: str | None = None
    conflict: str | None = None
    note: str | None = None


@dataclass
class Simulation:
    """Tracks the effect of earlier steps so later steps are checked against the planned state."""
    created_dirs: set[str] = field(default_factory=set)
    planned_dests: set[str] = field(default_factory=set)
    removed: set[str] = field(default_factory=set)

    @staticmethod
    def key(p: Path) -> str:
        return os.path.normcase(str(p))

    def exists(self, p: Path) -> bool:
        k = self.key(p)
        if k in self.removed:
            return False
        return p.exists() or k in self.created_dirs or k in self.planned_dests

    def is_dir(self, p: Path) -> bool:
        k = self.key(p)
        return (p.is_dir() and k not in self.removed) or k in self.created_dirs


class PolicyEngine:
    def __init__(self, settings: Settings, perms: Permissions, *, hosted: bool = False):
        self.settings = settings
        self.perms = perms
        self.hosted = hosted

    # ------------------------------------------------------------------ request screening
    def screen_request(self, text: str) -> ScreenResult | None:
        for category, risk, pattern, message in _SCREEN_RULES:
            if pattern.search(text or ""):
                return ScreenResult(category, risk, message)
        return None

    @property
    def desktop_available(self) -> bool:
        return IS_WINDOWS and not self.hosted

    # ------------------------------------------------------------------ per-action checks
    def check(self, action, sim: Simulation | None = None) -> StepCheck:
        sim = sim or Simulation()
        chk = StepCheck(risk=BASE_RISK[action.action])
        try:
            getattr(self, f"_check_{action.action}")(action, sim, chk)
        except PathViolation as exc:
            chk.violation = str(exc)
        return chk

    def _need_desktop(self, chk: StepCheck, web_ok: bool = True) -> bool:
        if not self.desktop_available and self.hosted and web_ok:
            chk.note = "Runs in the web virtual desktop (cloud sandbox) — the real app opens when run locally on Windows."
            return True
        if not self.desktop_available:
            chk.violation = ("Desktop application control is only available when the agent runs locally on "
                             "Windows (this is a hosted/sandbox session).")
            return False
        return True

    def _check_list_files(self, a: A.ListFiles, sim: Simulation, chk: StepCheck) -> None:
        p = self.perms.resolve(a.target)
        chk.targets = [a.target.display()]
        if not sim.is_dir(p):
            chk.violation = f"Folder {a.target.display()} does not exist."

    _check_find_duplicates = _check_list_files

    def _check_create_folder(self, a: A.CreateFolder, sim: Simulation, chk: StepCheck) -> None:
        p = self.perms.resolve(a.target, write=True)
        chk.targets = [a.target.display()]
        parent = self.perms.resolve(a.target.parent, write=True)
        if not sim.is_dir(parent):
            chk.violation = f"Parent folder {a.target.parent.display()} does not exist."
        elif sim.exists(p):
            if sim.is_dir(p):
                chk.note = "Folder already exists — this step will be skipped."
            else:
                chk.conflict = f"A file named '{a.target.name}' already exists at {a.target.parent.display()}."
        sim.created_dirs.add(sim.key(p))

    def _transfer(self, a, sim: Simulation, chk: StepCheck, *, move: bool) -> None:
        src = self.perms.resolve(a.source, write=move)
        dest_dir = self.perms.resolve(a.destination, write=True)
        name = a.new_name or a.source.name
        dest = dest_dir / name
        chk.targets = [a.source.display(), f"{a.destination.display().rstrip('/')}/{name}"]
        if not sim.exists(src):
            chk.violation = f"Source {a.source.display()} does not exist."
            return
        if not sim.is_dir(dest_dir):
            chk.violation = f"Destination folder {a.destination.display()} does not exist."
            return
        if sim.is_dir(src) and (sim.key(dest_dir) == sim.key(src) or str(sim.key(dest_dir)).startswith(sim.key(src) + os.sep)):
            chk.violation = "A folder cannot be copied or moved into itself."
            return
        if sim.key(dest) == sim.key(src):
            chk.note = "Source and destination are the same — nothing to do."
            return
        if sim.exists(dest):
            chk.conflict = f"'{name}' already exists in {a.destination.display()} — it will not be overwritten."
        sim.planned_dests.add(sim.key(dest))
        if move:
            sim.removed.add(sim.key(src))

    def _check_copy_file(self, a, sim, chk):
        self._transfer(a, sim, chk, move=False)

    def _check_move_file(self, a, sim, chk):
        self._transfer(a, sim, chk, move=True)

    def _check_rename_file(self, a: A.RenameFile, sim: Simulation, chk: StepCheck) -> None:
        src = self.perms.resolve(a.source, write=True)
        dest_ref = a.source.parent.child(a.new_name)
        dest = self.perms.resolve(dest_ref, write=True)
        chk.targets = [a.source.display(), dest_ref.display()]
        if not sim.exists(src):
            chk.violation = f"{a.source.display()} does not exist."
            return
        if sim.key(src) == sim.key(dest) and a.source.name == a.new_name:
            chk.note = "New name equals the current name — nothing to do."
            return
        if sim.exists(dest) and sim.key(src) != sim.key(dest):
            chk.conflict = f"'{a.new_name}' already exists — it will not be overwritten."
        sim.removed.add(sim.key(src))
        sim.removed.discard(sim.key(dest))
        sim.planned_dests.add(sim.key(dest))

    def _check_delete_file(self, a: A.DeleteFile, sim: Simulation, chk: StepCheck) -> None:
        p = self.perms.resolve(a.target, write=True)
        chk.targets = [a.target.display()]
        if not a.target.path:
            chk.violation = "An approved root folder itself cannot be deleted."
        elif not sim.exists(p):
            chk.violation = f"{a.target.display()} does not exist."
        sim.removed.add(sim.key(p))

    def _check_write_text_file(self, a: A.WriteTextFile, sim: Simulation, chk: StepCheck) -> None:
        p = self.perms.resolve(a.target, write=True)
        chk.targets = [a.target.display()]
        ext = Path(a.target.name).suffix.lower().lstrip(".")
        if ext not in TEXT_WRITE_EXTS:
            chk.violation = f"Only plain-text files can be created ({', '.join(sorted(TEXT_WRITE_EXTS))})."
            return
        if not sim.is_dir(self.perms.resolve(a.target.parent, write=True)):
            chk.violation = f"Folder {a.target.parent.display()} does not exist."
        elif sim.exists(p):
            chk.conflict = f"'{a.target.name}' already exists — it will not be overwritten."
        sim.planned_dests.add(sim.key(p))

    def _check_archive_folder(self, a: A.ArchiveFolder, sim: Simulation, chk: StepCheck) -> None:
        src = self.perms.resolve(a.target)
        dest = self.perms.resolve(a.destination, write=True)
        chk.targets = [a.target.display(), a.destination.display()]
        if not a.destination.name.lower().endswith(".zip"):
            chk.violation = "Archives must be .zip files."
        elif not sim.is_dir(src):
            chk.violation = f"Folder {a.target.display()} does not exist."
        elif not sim.is_dir(self.perms.resolve(a.destination.parent, write=True)):
            chk.violation = f"Folder {a.destination.parent.display()} does not exist."
        elif sim.exists(dest):
            chk.conflict = f"'{a.destination.name}' already exists — it will not be overwritten."
        sim.planned_dests.add(sim.key(dest))

    def _app_check(self, name: str, chk: StepCheck, *, automation: bool = False) -> None:
        app = self.perms.find_app(name)
        chk.targets = [app.name if app else name]
        if not app:
            chk.violation = (f"'{name}' is not on the application allowlist "
                             f"({', '.join(self.perms.app_names()) or 'empty'}). Add it in Settings → Applications.")
            return
        if automation and not app.automatable:
            chk.violation = f"{app.name} is allowlisted for launching only; UI automation is not enabled for it."
            return
        self._need_desktop(chk, web_ok=app.name.lower() in WEB_APPS)

    def _check_launch_app(self, a: A.LaunchApp, sim, chk):
        self._app_check(a.app, chk)

    def _check_inspect_ui(self, a: A.InspectUI, sim, chk):
        self._app_check(a.app, chk)

    def _check_type_text(self, a: A.TypeText, sim, chk):
        self._app_check(a.app, chk, automation=True)

    def _check_open_file(self, a: A.OpenFile, sim: Simulation, chk: StepCheck) -> None:
        p = self.perms.resolve(a.target)
        chk.targets = [a.target.display()]
        ext = Path(a.target.name).suffix.lower().lstrip(".")
        if ext in EXECUTABLE_EXTS:
            chk.violation = f"Opening executable or script files (.{ext}) is not allowed."
        elif not sim.exists(p) or sim.is_dir(p):
            chk.violation = f"File {a.target.display()} does not exist."
        else:
            self._need_desktop(chk)

    def _check_open_folder(self, a: A.OpenFolder, sim: Simulation, chk: StepCheck) -> None:
        p = self.perms.resolve(a.target)
        chk.targets = [a.target.display()]
        if not sim.is_dir(p):
            chk.violation = f"Folder {a.target.display()} does not exist."
        else:
            self._need_desktop(chk)

    # ------------------------------------------------------------------ web, programs, windows
    def _check_open_url(self, a: A.OpenUrl, sim, chk: StepCheck) -> None:
        from urllib.parse import urlsplit
        chk.targets = [urlsplit(a.url).hostname or a.url]
        if self.hosted:
            chk.note = "Cloud sandbox: the page appears as a link window — click it to open it in your browser."

    def _check_compose_message(self, a: A.ComposeMessage, sim, chk: StepCheck) -> None:
        chk.targets = [f"{a.channel}: {a.to or '(you choose the recipient)'}"]
        chk.note = "Opens a pre-filled draft only — the agent never sends. Review it and press Send yourself."

    def _check_launch_program(self, a: A.LaunchProgram, sim, chk: StepCheck) -> None:
        from app.actions import pc_control
        chk.targets = [a.name]
        if not self._need_desktop(chk, web_ok=False):
            return
        if a.name not in pc_control.program_index():
            best, alts = pc_control.find_program(a.name)
            chk.violation = (f"'{a.name}' is not an installed Start-menu program"
                             + (f" — did you mean {', '.join(alts or [best])}?" if (alts or best) else "."))
            return
        chk.note = "Installed program that is not on the allowlist, so it needs your approval."

    def _check_list_windows(self, a: A.ListWindows, sim, chk: StepCheck) -> None:
        chk.targets = ["open windows"]
        self._need_desktop(chk, web_ok=True)

    def _check_window_control(self, a: A.WindowControl, sim, chk: StepCheck) -> None:
        chk.targets = [a.window]
        if a.op == "close":
            chk.risk = Risk.MEDIUM
        if self._need_desktop(chk, web_ok=True) and a.op == "close" and not self.hosted:
            chk.note = "Closes politely (like clicking X) — the app can still ask you to save unsaved work."

    def _check_browser_tab(self, a: A.BrowserTab, sim, chk: StepCheck) -> None:
        chk.targets = [f"{a.browser} browser"]
        if a.op == "close":
            chk.risk = Risk.MEDIUM
        self._need_desktop(chk, web_ok=False)

    def _check_take_screenshot(self, a: A.TakeScreenshot, sim: Simulation, chk: StepCheck) -> None:
        p = self.perms.resolve(a.destination, write=True)
        chk.targets = [a.destination.display()]
        if not sim.is_dir(p):
            chk.violation = f"Folder {a.destination.display()} does not exist."
        elif self._need_desktop(chk, web_ok=False):
            chk.note = "Captures everything visible on your screen(s) into a PNG inside the approved folder."

    # ------------------------------------------------------------------ whole plans
    def evaluate(self, plan: Plan) -> Plan:
        """Assign risk/confirmation to every step and decide whether the plan needs approval."""
        pol = self.settings.policy
        sim = Simulation()
        for step in plan.steps:
            chk = self.check(step.action, sim)
            step.risk, step.targets = chk.risk, chk.targets or step.targets
            step.violation, step.conflict, step.note = chk.violation, chk.conflict, chk.note
        n = len(plan.steps)
        creates = sum(1 for s in plan.steps if s.action.action == "create_folder")
        deletes = sum(1 for s in plan.steps if s.action.action == "delete_file")
        if creates > 1:  # creating several folders is a batch change
            for s in plan.steps:
                if s.action.action == "create_folder":
                    s.risk = max_risk([s.risk, Risk.MEDIUM])
        if n > pol.max_actions_per_run:
            plan.blocked_reason = (f"This plan has {n} actions; the limit per run is {pol.max_actions_per_run} "
                                   "(Settings → Safety). Narrow the request.")
        if deletes > pol.max_bulk_delete:
            plan.blocked_reason = (f"This plan would delete {deletes} items; bulk deletes are limited to "
                                   f"{pol.max_bulk_delete} per run.")
        for s in plan.steps:
            s.requires_confirmation = s.risk == Risk.HIGH and pol.jit_confirm_high
        plan.risk = max_risk(s.risk for s in plan.steps)
        plan.requires_approval = self.approval_required(plan)
        return plan

    def approval_required(self, plan: Plan) -> bool:
        if plan.dry_run:
            return False  # a dry run only simulates; nothing on disk changes
        if plan.risk == Risk.HIGH:
            return True
        return plan.risk == Risk.MEDIUM and self.settings.policy.require_approval_medium

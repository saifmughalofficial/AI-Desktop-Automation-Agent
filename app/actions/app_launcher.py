"""Launch allowlisted applications and open approved files/folders.

Commands come only from the allowlist in Settings and are started with
shell=False — user or model text is never passed to a shell."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from app.actions import ui_automation
from app.config.settings import AppEntry
from app.runtime import IS_WINDOWS

BLOCKED_PROGRAMS = {
    "cmd", "powershell", "pwsh", "wscript", "cscript", "mshta", "regedit", "reg", "rundll32", "regsvr32", "msiexec",
    "schtasks", "sc", "bcdedit", "diskpart", "format", "net", "net1", "netsh", "taskkill", "certutil", "bitsadmin",
    "wmic", "curl", "wget", "bash", "wsl", "python", "pythonw", "py", "node", "java", "javaw", "vssadmin", "cipher",
    "takeown", "icacls", "runas", "explorer", "conhost", "wt", "ssh", "ftp", "tftp", "mmc", "gpedit", "secpol",
}


@dataclass
class LaunchResult:
    ok: bool
    verified: bool
    message: str
    pid: int | None = None
    handle: int | None = None


def resolve_command(entry: AppEntry) -> str | None:
    cmd = os.path.expandvars(entry.command.strip().strip('"'))
    if Path(cmd).is_absolute():
        return cmd if Path(cmd).is_file() else None
    return shutil.which(cmd)


def validate_app_command(command: str) -> str:
    """Used by Settings when a user adds an app: must be a real .exe and not a shell/system tool."""
    cmd = os.path.expandvars((command or "").strip().strip('"'))
    if not cmd.lower().endswith(".exe"):
        raise ValueError("Only .exe programs can be allowlisted.")
    if Path(cmd).stem.lower() in BLOCKED_PROGRAMS:
        raise ValueError(f"{Path(cmd).name} is a shell or system tool and cannot be allowlisted.")
    resolved = cmd if Path(cmd).is_absolute() else shutil.which(cmd)
    if not resolved or not Path(resolved).is_file():
        raise ValueError(f"Program not found: {cmd}")
    return cmd


def launch(entry: AppEntry, timeout: float = 6.0) -> LaunchResult:
    if not IS_WINDOWS:
        return LaunchResult(False, False, "Launching applications requires Windows.")
    if Path(entry.command).stem.lower() in BLOCKED_PROGRAMS:
        return LaunchResult(False, False, f"{entry.command} is a blocked program.")
    exe = resolve_command(entry)
    if not exe:
        return LaunchResult(False, False, f"{entry.name} is not installed on this PC ({entry.command} not found).")
    before = ui_automation.window_handles(entry.window_title)
    try:
        proc = subprocess.Popen([exe], shell=False, close_fds=True)
    except OSError as exc:
        return LaunchResult(False, False, f"Could not start {entry.name}: {exc.strerror or exc}")
    handle = None
    if entry.window_title and ui_automation.available()[0]:
        handle = ui_automation.wait_for_new_window(entry.window_title, before, timeout)
        if handle:
            return LaunchResult(True, True, f"{entry.name} started; its window was detected.", proc.pid, handle)
        return LaunchResult(True, False, f"{entry.name} was started but no new window appeared within "
                                         f"{timeout:.0f}s, so success could not be verified.", proc.pid)
    time.sleep(1.0)
    running = proc.poll() is None
    return LaunchResult(True, running, f"{entry.name} started (process {'running' if running else 'exited'}; "
                                       "window not verifiable without pywinauto).", proc.pid)


def open_with_default_app(path: Path) -> LaunchResult:
    if not hasattr(os, "startfile"):
        return LaunchResult(False, False, "Opening files with their default app requires Windows.")
    os.startfile(str(path))  # noqa: S606 - path is resolved inside an approved root and is not executable
    return LaunchResult(True, False, f"Handed {path.name} to its default application. Windows does not report "
                                     "whether that app opened successfully, so this is unverified.")


def open_folder(path: Path, timeout: float = 4.0) -> LaunchResult:
    if not hasattr(os, "startfile"):
        return LaunchResult(False, False, "Opening folders in Explorer requires Windows.")
    title = f"^{re.escape(path.name)}$"
    before = ui_automation.window_handles(title)
    os.startfile(str(path))  # noqa: S606 - approved directory
    handle = ui_automation.wait_for_new_window(title, before, timeout) if ui_automation.available()[0] else None
    if handle:
        return LaunchResult(True, True, f"Explorer opened {path.name}; window detected.", handle=handle)
    return LaunchResult(True, False, f"Asked Explorer to open {path.name}; its window could not be verified "
                                     "(Explorer may have reused an existing window).")


def open_mailto(url: str) -> tuple[bool, str]:
    """Open a mailto: draft in the default mail app (Windows), else the default browser."""
    if not url.startswith("mailto:"):
        return False, "Not a mailto: link."
    try:
        if hasattr(os, "startfile"):
            os.startfile(url)  # noqa: S606 - a mailto: URL built by compose_url, never a path
            return True, "Opened the default mail app."
        import webbrowser
        return webbrowser.open(url), "Opened the default mail handler."
    except OSError as exc:
        return False, f"No email app is set up on this PC ({exc}). Try 'draft a Gmail' or 'draft an Outlook email'."

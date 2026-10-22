"""Limited, accessibility-based UI automation (Windows UI Automation via pywinauto).

Controls are located through the accessibility tree, never by screen coordinates.
Typing is only allowed into windows this agent launched itself in this session."""
from __future__ import annotations

import re
import time

from app.runtime import IS_WINDOWS

_SPECIAL = set("+^%~(){}[]")


def available() -> tuple[bool, str]:
    if not IS_WINDOWS:
        return False, "UI automation needs Windows."
    try:
        import sys
        if "pywinauto" not in sys.modules:
            sys.coinit_flags = 2  # STA: what Streamlit's threads need; avoids pywinauto's COM-mode warning
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import pywinauto  # noqa: F401
    except Exception as exc:  # pragma: no cover - depends on install
        return False, f"pywinauto is not installed ({exc.__class__.__name__}). Run setup.bat."
    return True, "Windows UI Automation (pywinauto, UIA backend)"


def _com_init() -> None:
    """pywinauto's UIA backend uses COM, which must be initialised in every thread."""
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass


def _desktop():
    _com_init()
    from pywinauto import Desktop
    return Desktop(backend="uia")


def window_handles(title_re: str) -> set[int]:
    if not title_re or not available()[0]:
        return set()
    try:
        pattern = re.compile(title_re)
        return {w.handle for w in _desktop().windows(top_level_only=True)
                if pattern.search(w.window_text() or "")}
    except Exception:
        return set()


def wait_for_new_window(title_re: str, before: set[int], timeout: float) -> int | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        new = window_handles(title_re) - before
        if new:
            return max(new)
        time.sleep(0.25)
    return None


def window_exists(handle: int) -> bool:
    try:
        return _desktop().window(handle=handle).exists(timeout=0.5)
    except Exception:
        return False


def inspect_window(title_re: str, handle: int | None = None, limit: int = 150) -> list[dict]:
    """Read-only: enumerate accessible controls of a matching window."""
    desk = _desktop()
    if handle and window_exists(handle):
        win = desk.window(handle=handle)
    else:
        handles = window_handles(title_re)
        if not handles:
            raise LookupError("No open window of this application was found. Launch it first.")
        win = desk.window(handle=max(handles))
    rows = [{"depth": 0, "control_type": win.element_info.control_type, "name": win.window_text(),
             "automation_id": win.element_info.automation_id or "", "enabled": win.is_enabled()}]
    for ctrl in win.descendants()[: limit - 1]:
        info = ctrl.element_info
        rows.append({"depth": 1, "control_type": info.control_type or "", "name": (info.name or "")[:80],
                     "automation_id": info.automation_id or "", "enabled": bool(info.enabled)})
    return rows


def _escape_keys(text: str) -> str:
    return "".join("{%s}" % c if c in _SPECIAL else c for c in text)


def _editor(win):
    for ctype in ("Document", "Edit"):
        try:
            ctrl = win.child_window(control_type=ctype, found_index=0)
            if ctrl.exists(timeout=1.5):
                return ctrl.wrapper_object()
        except Exception:
            continue
    raise LookupError("No editable text control found in the window (accessibility tree).")


def _read_text(ctrl) -> str:
    for getter in (lambda: ctrl.get_value(), lambda: ctrl.iface_value.CurrentValue,
                   lambda: "\n".join(ctrl.texts())):
        try:
            value = getter()
            if value:
                return str(value)
        except Exception:
            continue
    return ""


def type_text(handle: int, text: str, timeout: float = 6.0) -> tuple[bool, str]:
    """Append text to the editor control of a window the agent launched, then read it back."""
    desk = _desktop()
    win = desk.window(handle=handle)
    win.wait("exists ready", timeout=timeout)
    editor = _editor(win)
    win.set_focus()
    editor.set_focus()
    editor.type_keys("^{END}", set_foreground=True)
    editor.type_keys(_escape_keys(text), with_spaces=True, with_newlines=True, with_tabs=True, pause=0.01,
                     set_foreground=True)
    time.sleep(0.3)
    content = _read_text(editor).replace("\r\n", "\n").replace("\r", "\n")
    if text.replace("\r\n", "\n") in content:
        return True, "Typed text verified by reading the editor control back."
    return False, "Typing was sent but the text could not be read back from the control."

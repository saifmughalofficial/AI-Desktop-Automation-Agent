"""Whole-PC helpers: browser/web, message drafts, installed programs, windows, tabs, screenshots.

Nothing here calls a shell. URLs are validated by the schema (http/https only),
programs come from the Start-menu index (never from free text), and windows are
driven through Windows UI Automation. Message drafts only *open* a compose
window — the user reviews and presses Send themselves; the agent never sends."""
from __future__ import annotations

import difflib
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import webbrowser
from pathlib import Path

from app.actions import ui_automation
from app.actions.app_launcher import BLOCKED_PROGRAMS
from app.runtime import IS_WINDOWS

# ---------------------------------------------------------------- web
SITES = {
    "youtube": "https://www.youtube.com", "gmail": "https://mail.google.com", "google": "https://www.google.com",
    "google drive": "https://drive.google.com", "drive": "https://drive.google.com",
    "google maps": "https://maps.google.com", "maps": "https://maps.google.com",
    "google translate": "https://translate.google.com", "translate": "https://translate.google.com",
    "facebook": "https://www.facebook.com", "instagram": "https://www.instagram.com", "twitter": "https://x.com",
    "x": "https://x.com", "linkedin": "https://www.linkedin.com", "github": "https://github.com",
    "whatsapp": "https://web.whatsapp.com", "whatsapp web": "https://web.whatsapp.com",
    "wikipedia": "https://www.wikipedia.org", "reddit": "https://www.reddit.com", "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.com", "outlook": "https://outlook.live.com", "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com", "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai",
    "spotify": "https://open.spotify.com", "tiktok": "https://www.tiktok.com", "pinterest": "https://www.pinterest.com",
    "telegram": "https://web.telegram.org", "discord": "https://discord.com/app", "news": "https://news.google.com",
    "weather": "https://www.google.com/search?q=weather", "streamlit": "https://streamlit.io",
}
ENGINES = {
    "google": "https://www.google.com/search?q={q}", "youtube": "https://www.youtube.com/results?search_query={q}",
    "bing": "https://www.bing.com/search?q={q}", "duckduckgo": "https://duckduckgo.com/?q={q}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={q}", "amazon": "https://www.amazon.com/s?k={q}",
    "github": "https://github.com/search?q={q}", "maps": "https://www.google.com/maps/search/{q}",
    "images": "https://www.google.com/search?tbm=isch&q={q}", "news": "https://news.google.com/search?q={q}",
}
TLDS = r"(?:com|org|net|io|ai|dev|app|edu|gov|pk|in|uk|co|me|info|tv|us|de|fr|ca|au|ae|sa|tr|ru|cn|jp|xyz|site|online|tech|biz|ly|gg)"
DOMAIN_RE = re.compile(rf"^(?:https?://)?(?:[a-z0-9-]+\.)+{TLDS}(?:[:/?#]\S*)?$", re.I)


def search_url(query: str, engine: str = "google") -> str:
    return ENGINES.get(engine, ENGINES["google"]).format(q=urllib.parse.quote_plus(query.strip()))


def normalize_url(text: str) -> str | None:
    t = text.strip().strip("<>\"'")
    if DOMAIN_RE.match(t):
        return t if t.lower().startswith(("http://", "https://")) else f"https://{t}"
    return None


def compose_url(channel: str, to: str, subject: str, body: str) -> str:
    q = urllib.parse.quote
    if channel == "whatsapp":
        phone = re.sub(r"[^\d]", "", to)
        return f"https://wa.me/{phone}?text={q(body)}" if phone else f"https://wa.me/?text={q(body)}"
    if channel == "gmail":
        return (f"https://mail.google.com/mail/?view=cm&fs=1&to={q(to)}&su={q(subject)}&body={q(body)}")
    if channel == "outlook":
        return (f"https://outlook.live.com/mail/0/deeplink/compose?to={q(to)}&subject={q(subject)}&body={q(body)}")
    return f"mailto:{q(to, safe='@,;')}?subject={q(subject)}&body={q(body)}"


_BROWSER_EXES = {
    "chrome": [r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
               r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
               r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe", "chrome"],
    "edge": [r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
             r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe", "msedge"],
    "firefox": [r"%ProgramFiles%\Mozilla Firefox\firefox.exe", r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
                "firefox"],
}
BROWSER_PROCS = {"chrome": "chrome.exe", "edge": "msedge.exe", "firefox": "firefox.exe"}


def browser_exe(name: str) -> str | None:
    for cand in _BROWSER_EXES.get(name, []):
        p = os.path.expandvars(cand)
        if Path(p).is_absolute() and Path(p).is_file():
            return p
        if not Path(p).is_absolute() and (w := shutil.which(p)):
            return w
    return None


def open_url(url: str, browser: str = "default") -> tuple[bool, str]:
    if browser != "default":
        exe = browser_exe(browser)
        if not exe:
            return False, f"{browser.title()} is not installed on this PC."
        try:
            subprocess.Popen([exe, url], shell=False, close_fds=True)
        except OSError as exc:
            return False, f"Could not start {browser.title()}: {exc}"
        return True, f"Opened {url} in {browser.title()}."
    ok = webbrowser.open(url, new=2)
    return ok, f"Opened {url} in your default browser." if ok else "No web browser could be opened."


# ---------------------------------------------------------------- installed programs (Start menu)
_PROGRAM_BLOCK = re.compile(r"uninstall|setup|install|command prompt|powershell|terminal|registry|regedit|"
                            r"cmd\b|bash|wsl|console|debug|recovery|reset|disk ?part|format|task scheduler|services|"
                            r"computer management|group policy|security policy|readme|license|help|website|"
                            r"documentation|release notes", re.I)
_index: dict = {"t": 0.0, "items": {}}


def _start_menu_dirs() -> list[Path]:
    dirs = [Path(os.environ.get("ProgramData", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
            Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs"]
    return [d for d in dirs if d.is_dir()]


def program_index(refresh: bool = False) -> dict[str, Path]:
    """name -> .lnk path for installed programs listed in the Start menu (blocked tools removed)."""
    if not IS_WINDOWS:
        return {}
    if not refresh and _index["items"] and time.monotonic() - _index["t"] < 300:
        return _index["items"]
    items: dict[str, Path] = {}
    for d in _start_menu_dirs():
        for lnk in d.rglob("*.lnk"):
            name = lnk.stem.strip()
            if _PROGRAM_BLOCK.search(name) or name.lower() in BLOCKED_PROGRAMS:
                continue
            items.setdefault(name, lnk)
    _index.update(t=time.monotonic(), items=items)
    return items


def program_names() -> list[str]:
    return sorted(program_index())


PROGRAM_ALIASES = {"vs code": "visual studio code", "vscode": "visual studio code", "code": "visual studio code",
                   "chrome": "google chrome", "edge": "microsoft edge", "firefox": "firefox", "word": "word",
                   "ms word": "word", "excel": "excel", "ms excel": "excel", "powerpoint": "powerpoint", "ppt": "powerpoint",
                   "teams": "microsoft teams", "store": "microsoft store", "settings": "settings",
                   "task manager": "task manager", "snipping tool": "snipping tool", "photos": "photos",
                   "camera": "camera", "media player": "media player", "vlc": "vlc media player"}


def find_program(query: str, names: list[str] | None = None) -> tuple[str | None, list[str]]:
    """Best installed-program match for ``query`` plus close alternatives (for 'did you mean')."""
    names = names if names is not None else program_names()
    q = re.sub(r"\s+(?:app|application|program)$", "", query.strip().lower())
    q = PROGRAM_ALIASES.get(q, q)
    if not q or not names:
        return None, []
    low = {n.lower(): n for n in names}
    if q in low:
        return low[q], []
    starts = [n for n in names if n.lower().startswith(q)]
    if len(starts) == 1:
        return starts[0], []
    words = [n for n in names if re.search(rf"\b{re.escape(q)}\b", n.lower())]
    if len(words) == 1:
        return words[0], []
    close = difflib.get_close_matches(q, list(low), n=4, cutoff=0.72)
    if close and (len(close) == 1 or difflib.SequenceMatcher(None, q, close[0]).ratio() > 0.86):
        return low[close[0]], [low[c] for c in close[1:]]
    return None, (starts or words or [low[c] for c in close])[:5]


def _top_windows() -> list:
    """Real app windows, including minimized ones (UIA's visible_only skips minimized windows)."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        return [w for w in ui_automation._desktop().windows(top_level_only=True, visible_only=False)
                if (w.window_text() or "").strip() not in {"", "Program Manager", "Taskbar"}
                and user32.IsWindowVisible(w.handle) and not user32.GetWindow(w.handle, 4)]  # 4 = GW_OWNER
    except Exception:
        return []


def launch_program(name: str, timeout: float = 8.0) -> tuple[bool, bool, str]:
    lnk = program_index().get(name)
    if not lnk:
        return False, False, f"{name} is not in the Start-menu program list."
    before = {w.handle for w in _top_windows()}
    os.startfile(str(lnk))  # noqa: S606 - a Start-menu shortcut from the index, never user text
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        new = [w for w in _top_windows() if w.handle not in before]
        if new:
            return True, True, f"{name} started; new window “{new[0].window_text()[:60]}” detected."
        time.sleep(0.4)
    return True, False, f"{name} was started, but no new window appeared within {timeout:.0f}s (it may already be open)."


# ---------------------------------------------------------------- windows
def _proc_name(w) -> str:
    try:
        import psutil
        return psutil.Process(w.process_id()).name()
    except Exception:
        return ""


def list_windows(filter_text: str = "") -> list[dict]:
    rows = []
    for w in _top_windows():
        title = w.window_text()
        proc = _proc_name(w)
        if filter_text and filter_text.lower() not in f"{title} {proc}".lower():
            continue
        try:
            state = "minimized" if w.is_minimized() else ("maximized" if w.is_maximized() else "normal")
        except Exception:
            state = ""
        rows.append({"title": title[:90], "process": proc, "state": state, "handle": w.handle})
    return rows


def find_window(query: str) -> tuple[object | None, list[str]]:
    q = query.strip().lower()
    q = re.sub(r"^(?:the|my)\s+|\s+(?:window|app|application|browser)$", "", q).strip()
    wins = _top_windows()
    if not q or not wins:
        return None, []
    aliases = {"chrome": "chrome.exe", "google chrome": "chrome.exe", "edge": "msedge.exe", "firefox": "firefox.exe",
               "file explorer": "explorer.exe", "explorer": "explorer.exe", "word": "winword.exe",
               "excel": "excel.exe", "powerpoint": "powerpnt.exe", "vs code": "code.exe", "vscode": "code.exe"}
    proc_target = aliases.get(q, q if q.endswith(".exe") else f"{q}.exe")
    scored = []
    for w in wins:
        title, proc = w.window_text().lower(), _proc_name(w).lower()
        if proc == proc_target:
            scored.append((3, w))
        elif q in title:
            scored.append((2, w))
        else:
            r = max(difflib.SequenceMatcher(None, q, proc.removesuffix(".exe")).ratio(),
                    max((difflib.SequenceMatcher(None, q, part).ratio() for part in re.split(r"[-–|—]", title)), default=0))
            if r >= 0.75:
                scored.append((r, w))
    if not scored:
        return None, [w.window_text()[:50] for w in wins[:6]]
    scored.sort(key=lambda s: -s[0])
    return scored[0][1], []


def window_op(win, op: str) -> tuple[bool, str]:
    title = win.window_text()[:60]
    if op == "focus":
        if win.is_minimized():
            win.restore()
        win.set_focus()
        time.sleep(0.3)
        return True, f"Switched to “{title}”."
    if op == "minimize":
        win.minimize()
        time.sleep(0.3)
        return bool(win.is_minimized()), f"Minimized “{title}”."
    if op == "maximize":
        win.maximize()
        time.sleep(0.3)
        return bool(win.is_maximized()), f"Maximized “{title}”."
    if op == "restore":
        win.restore()
        time.sleep(0.3)
        return not win.is_minimized(), f"Restored “{title}”."
    if op == "close":
        handle = win.handle
        win.close()  # polite WM_CLOSE: the app can still ask to save unsaved work
        time.sleep(1.0)
        gone = handle not in {w.handle for w in _top_windows()}
        return gone, (f"Closed “{title}”." if gone else f"Asked “{title}” to close — it may be showing a save prompt.")
    return False, f"Unknown window operation '{op}'."


TAB_KEYS = {"new": "^t", "close": "^w", "next": "^{TAB}", "previous": "^+{TAB}", "reload": "{F5}"}


def browser_tab(op: str, browser: str = "any") -> tuple[bool, str]:
    procs = set(BROWSER_PROCS.values()) if browser == "any" else {BROWSER_PROCS[browser]}
    wins = [w for w in _top_windows() if _proc_name(w).lower() in procs]
    if not wins:
        return False, "No open browser window was found. Open a website first."
    win = wins[0]
    before = win.window_text()
    if win.is_minimized():
        win.restore()
    win.set_focus()
    time.sleep(0.25)
    from pywinauto import keyboard
    keyboard.send_keys(TAB_KEYS[op])
    time.sleep(0.8)
    after = win.window_text() if win.exists() else ""
    changed = after != before or op == "reload"
    return True, (f"Browser tab: {op} (now “{after[:60]}”)." if changed else f"Browser tab: {op} sent.")


def screenshot(dest: Path) -> tuple[bool, str]:
    from PIL import ImageGrab
    img = ImageGrab.grab(all_screens=True)
    img.save(dest, "PNG")
    return dest.is_file() and dest.stat().st_size > 1000, f"Saved a {img.width}×{img.height} screenshot."

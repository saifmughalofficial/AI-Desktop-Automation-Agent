"""Web virtual desktop — used when the agent is hosted (e.g. Streamlit Cloud).

A web server cannot control a visitor's PC, so in hosted mode app actions open
working in-browser windows instead (Notepad, Calculator, Paint, Character Map,
file viewer, folder viewer). They go through the same planner, policy,
approval and verification as the real Windows automation."""
from __future__ import annotations

import itertools
import threading
from pathlib import Path

WEB_APPS = {"notepad", "wordpad", "calculator", "paint", "character map"}
TEXT_PREVIEW = {"txt", "md", "csv", "json", "log", "py", "html", "css", "xml", "yml", "yaml", "ini", "toml"}
IMAGE_PREVIEW = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}


class VirtualDesktop:
    def __init__(self):
        self.windows: dict[str, dict] = {}
        self._ids = itertools.count(1)
        self._lock = threading.RLock()

    @staticmethod
    def supports(app_name: str) -> bool:
        return app_name.strip().lower() in WEB_APPS

    def _new(self, kind: str, title: str, **data) -> dict:
        with self._lock:
            wid = f"w{next(self._ids)}"
            win = {"id": wid, "kind": kind, "title": title, "rev": 0, **data}
            self.windows[wid] = win
            return win

    def open_app(self, name: str) -> dict:
        kind = name.strip().lower()
        title = {"notepad": "Untitled - Notepad", "wordpad": "Document - WordPad"}.get(kind, name)
        return self._new(kind, title, text="")

    def get(self, wid: str | None) -> dict | None:
        return self.windows.get(wid) if wid else None

    def type_text(self, wid: str, text: str) -> tuple[bool, str]:
        with self._lock:
            win = self.windows.get(wid)
            if not win or "text" not in win:
                return False, "The editor window is no longer open."
            win["text"] += text
            win["rev"] += 1
            ok = text in win["text"]  # read back
        return ok, "Typed text verified by reading the editor back." if ok else "Text could not be read back."

    def controls(self, wid: str) -> list[dict]:
        win = self.windows.get(wid)
        if not win:
            return []
        base = [{"depth": 0, "control_type": "Window", "name": win["title"], "automation_id": wid, "enabled": True},
                {"depth": 1, "control_type": "TitleBar", "name": win["title"], "automation_id": "title", "enabled": True},
                {"depth": 1, "control_type": "Button", "name": "Close", "automation_id": "close", "enabled": True}]
        extra = {"notepad": [("Document", "Text editor", "editor")], "wordpad": [("Document", "Rich text", "editor")],
                 "calculator": [("Text", "Display", "display")] + [("Button", k, f"key_{k}") for k in "0123456789+-*/=C"],
                 "paint": [("Pane", "Canvas", "canvas"), ("Button", "Clear", "clear"), ("Button", "Save PNG", "save")],
                 "character map": [("List", "Characters", "grid")]}.get(win["kind"], [])
        return base + [{"depth": 1, "control_type": t, "name": n, "automation_id": a, "enabled": True} for t, n, a in extra]

    def open_file(self, display: str, path: Path) -> dict:
        ext = path.suffix.lower().lstrip(".")
        if ext in IMAGE_PREVIEW:
            return self._new("image", f"{path.name} - Photos", path=str(path))
        if ext in TEXT_PREVIEW and path.stat().st_size <= 300_000:
            return self._new("viewer", f"{path.name} - Viewer", content=path.read_text(encoding="utf-8", errors="replace"))
        return self._new("info", f"{path.name} - Properties", content=f"{display}\n{path.stat().st_size} bytes\n"
                                                                        "(no in-browser preview for this file type)")

    def open_folder(self, display: str, rows: list[dict]) -> dict:
        return self._new("explorer", f"{display} - File Explorer", rows=rows)

    def open_link(self, title: str, url: str, draft: dict | None = None) -> dict:
        from urllib.parse import urlsplit
        host = urlsplit(url).hostname or "link"
        name = title if title != url else f"{host} - Browser"
        return self._new("link", name, url=url, draft=draft or {})

    def find(self, query: str) -> dict | None:
        q = query.strip().lower()
        q = q.removesuffix(" window").removeprefix("the ").strip()
        hits = [w for w in self.windows.values() if q and (q in w["title"].lower() or q == w["kind"])]
        return hits[-1] if hits else None

    def close(self, wid: str) -> None:
        with self._lock:
            self.windows.pop(wid, None)

    def latest(self, kind: str) -> dict | None:
        wins = [w for w in self.windows.values() if w["kind"] == kind]
        return wins[-1] if wins else None

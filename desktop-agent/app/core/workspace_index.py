"""A read-only index of folder and file names inside the approved roots.

Used by the planners to turn phrases like "my Projects directory" or
"notes.txt" into sandboxed PathRefs. It never reads file contents."""
from __future__ import annotations

import os
import re
from pathlib import Path

from app.core.action_schema import PathRef
from app.core.permissions import Permissions, TRASH_DIR


def norm(text: str) -> str:
    return re.sub(r"[\s_\-]+", "", (text or "").lower()).strip(" .'\"")


class WorkspaceIndex:
    def __init__(self, perms: Permissions, max_entries: int = 8000, max_depth: int = 5):
        self.perms = perms
        self.roots: list[PathRef] = []
        self.root_names: dict[str, str] = {}  # normalised folder basename -> alias
        self.dirs: list[PathRef] = []
        self.files: list[PathRef] = []
        self.virtual_dirs: list[PathRef] = []
        count = 0
        for root in perms.roots:
            base = Path(os.path.realpath(root.path))
            if not base.is_dir():
                continue
            self.roots.append(PathRef(root=root.alias))
            self.root_names[norm(base.name)] = root.alias
            base_depth = len(base.parts)
            for dirpath, dirnames, filenames in os.walk(base):
                depth = len(Path(dirpath).parts) - base_depth
                dirnames[:] = [d for d in dirnames if d != TRASH_DIR and not d.startswith(".")] if depth < max_depth else []
                rel = Path(dirpath).relative_to(base).as_posix()
                rel = "" if rel == "." else rel
                for d in dirnames:
                    self.dirs.append(PathRef(root=root.alias, path=f"{rel}/{d}" if rel else d))
                for f in filenames:
                    if not f.startswith("."):
                        self.files.append(PathRef(root=root.alias, path=f"{rel}/{f}" if rel else f))
                count += len(dirnames) + len(filenames)
                if count > max_entries:
                    break

    # ------------------------------------------------------------------ lookups
    def root_for(self, phrase: str) -> PathRef | None:
        key = norm(phrase)
        for r in self.roots:
            if norm(r.root) == key:
                return r
        alias = self.root_names.get(key)
        return PathRef(root=alias) if alias else None

    def all_dirs(self) -> list[PathRef]:
        return self.dirs + self.virtual_dirs

    def find_dirs(self, phrase: str) -> list[PathRef]:
        text = phrase.strip().replace("\\", "/").strip("/")
        if "/" in text:
            tail = norm(text)
            return [d for d in self.all_dirs()
                    if norm(d.path).endswith(tail) and norm(d.path.split("/")[-1]) == norm(text.split("/")[-1])]
        key = norm(text)
        return [d for d in self.all_dirs() if norm(d.name) == key]

    def find_files(self, name: str, within: PathRef | None = None) -> list[PathRef]:
        key = name.strip().lower()
        out = [f for f in self.files if f.name.lower() == key]
        if within:
            prefix = f"{within.path}/" if within.path else ""
            out = [f for f in out if f.root == within.root and f.path.startswith(prefix)]
        return out

    def is_dir(self, ref: PathRef) -> bool:
        if not ref.path:
            return any(r.root == ref.root for r in self.roots)
        return any(d.root == ref.root and d.path.lower() == ref.path.lower() for d in self.all_dirs())

    def add_virtual_dir(self, ref: PathRef) -> None:
        if not self.is_dir(ref):
            self.virtual_dirs.append(ref)

    def files_in(self, folder: PathRef, extensions=()) -> list[PathRef]:
        """Top-level files of a folder (from disk, so it is always current)."""
        try:
            base = self.perms.resolve(folder)
        except Exception:
            return []
        if not base.is_dir():
            return []
        exts = {e.lower() for e in extensions}
        out = []
        for entry in sorted(os.scandir(base), key=lambda e: e.name.lower()):
            if entry.is_file() and not entry.name.startswith("."):
                if not exts or Path(entry.name).suffix.lower().lstrip(".") in exts:
                    out.append(folder.child(entry.name))
        return out

    def summary_for_model(self, limit: int = 60) -> str:
        """Folder names only (no contents) — context for the optional local model."""
        names = [r.display() for r in self.roots] + [d.display() for d in self.dirs[:limit]]
        return "Known folders: " + ", ".join(names)

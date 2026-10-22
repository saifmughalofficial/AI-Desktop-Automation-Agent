"""Read-only insights about the approved folders (counts and sizes by file type, largest files)."""
from __future__ import annotations

import os
from pathlib import Path

from app.actions.filesystem import category_for
from app.core.permissions import Permissions, TRASH_DIR


def workspace_stats(perms: Permissions, limit: int = 20000) -> dict:
    cats: dict[str, dict] = {}
    files = folders = total = 0
    largest: list[tuple[int, str]] = []
    trash = 0
    for root in perms.roots:
        base = Path(os.path.realpath(root.path))
        if not base.is_dir():
            continue
        tdir = base / TRASH_DIR
        if tdir.is_dir():
            trash += sum(1 for _ in tdir.iterdir())
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            folders += len(dirnames)
            for fn in filenames:
                if fn.startswith("."):
                    continue
                try:
                    size = os.path.getsize(os.path.join(dirpath, fn))
                except OSError:
                    continue
                c = cats.setdefault(category_for(fn), {"files": 0, "bytes": 0})
                c["files"] += 1
                c["bytes"] += size
                files += 1
                total += size
                rel = Path(dirpath, fn).relative_to(base).as_posix()
                largest.append((size, f"{root.alias}/{rel}"))
                if files >= limit:
                    break
    largest.sort(reverse=True)
    return {"files": files, "folders": folders, "bytes": total, "categories": dict(sorted(cats.items(), key=lambda kv: -kv[1]["files"])),
            "largest": largest[:3], "quarantined": trash, "roots": len(perms.roots)}

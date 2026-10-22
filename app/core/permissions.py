"""Approved-folder sandbox and application allowlist.

All file access goes through Permissions.resolve(), which canonicalises the path
(resolving symlinks and junctions) and rejects anything that ends up outside
the approved root. Raw absolute paths are never accepted from a plan."""
from __future__ import annotations

import os
from pathlib import Path

from app.config.settings import AppEntry, ApprovedRoot, Settings
from app.core.action_schema import PathRef, validate_relpath
from app.runtime import IS_WINDOWS

TRASH_DIR = ".agent_trash"


class PathViolation(Exception):
    """A path or app request that the sandbox refuses."""


def _norm(p: Path | str) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def is_within(child: Path | str, parent: Path | str) -> bool:
    c, p = _norm(child), _norm(parent)
    try:
        return os.path.commonpath([c, p]) == p
    except ValueError:  # different drives on Windows
        return False


def _system_dirs() -> list[Path]:
    if IS_WINDOWS:
        keys = ["SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData",
                "APPDATA", "LOCALAPPDATA"]
        return [Path(os.environ[k]) for k in keys if os.environ.get(k)]
    return [Path(p) for p in ("/bin", "/boot", "/dev", "/etc", "/lib", "/lib64", "/proc", "/sbin", "/sys",
                              "/usr", "/var", "/root")]


def check_root_candidate(raw: str) -> Path:
    """Validate a folder the user wants to approve. Rejects drive roots, the whole
    home folder and system/app-data folders (which hold credentials and settings)."""
    text = (raw or "").strip().strip('"').strip("'")
    if not text:
        raise PathViolation("Enter a folder path.")
    p = Path(os.path.expandvars(text)).expanduser()
    if not p.is_absolute():
        raise PathViolation("Use a full folder path, e.g. C:\\Users\\you\\Documents\\Projects.")
    real = Path(os.path.realpath(p))
    if not real.is_dir():
        raise PathViolation(f"Folder does not exist: {real}")
    if real.parent == real:
        raise PathViolation("A whole drive is too broad. Approve a specific folder instead.")
    if _norm(real) == _norm(Path.home()):
        raise PathViolation("Your entire home folder is too broad. Approve a subfolder such as Documents or Downloads.")
    for sys_dir in _system_dirs():
        if is_within(real, sys_dir) or is_within(sys_dir, real):
            raise PathViolation(f"System or application-data folders cannot be approved ({sys_dir}).")
    return real


class Permissions:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.roots: list[ApprovedRoot] = list(settings.approved_roots)
        self.apps: list[AppEntry] = list(settings.apps)

    # ------------------------------------------------------------------ roots
    def find_root(self, alias: str) -> ApprovedRoot:
        key = (alias or "").strip().lower()
        for root in self.roots:
            if root.alias.lower() == key:
                return root
        allowed = ", ".join(r.alias for r in self.roots) or "none configured"
        raise PathViolation(f"'{alias}' is not an approved folder (approved: {allowed}).")

    def root_path(self, alias: str) -> Path:
        return Path(os.path.realpath(self.find_root(alias).path))

    def resolve(self, ref: PathRef, *, write: bool = False, allow_trash: bool = False) -> Path:
        root = self.find_root(ref.root)
        base = Path(os.path.realpath(root.path))
        if not base.is_dir():
            raise PathViolation(f"Approved folder '{root.alias}' is missing on disk.")
        rel = validate_relpath(ref.path)  # defence in depth: PathRef already validated
        candidate = base.joinpath(*rel.split("/")) if rel else base
        real = Path(os.path.realpath(candidate))
        if not is_within(real, base):
            raise PathViolation(f"'{ref.display()}' resolves outside the approved folder (symlink/junction escape).")
        if not allow_trash and rel and rel.split("/")[0].lower() == TRASH_DIR:
            raise PathViolation("The agent quarantine folder (.agent_trash) cannot be targeted directly.")
        if write and root.access != "read_write":
            raise PathViolation(f"'{root.alias}' is approved for read-only access.")
        return real

    def to_ref(self, path: Path) -> PathRef | None:
        for root in self.roots:
            base = Path(os.path.realpath(root.path))
            if is_within(path, base):
                rel = Path(os.path.abspath(path)).relative_to(Path(os.path.abspath(base))) if _norm(path) != _norm(base) else Path("")
                return PathRef(root=root.alias, path=rel.as_posix() if str(rel) != "." else "")
        return None

    def trash_dir(self, alias: str) -> Path:
        return self.root_path(alias) / TRASH_DIR

    # ------------------------------------------------------------------ apps
    def find_app(self, name: str) -> AppEntry | None:
        key = (name or "").strip().lower()
        for app in self.apps:
            if app.matches(key):
                return app
        return None

    def app_names(self) -> list[str]:
        return [a.name for a in self.apps]

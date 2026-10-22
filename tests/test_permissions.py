"""Approved-folder sandbox: traversal, absolute paths, symlink/junction escapes, read-only roots, system dirs."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.action_schema import PathRef
from app.core.permissions import PathViolation, Permissions, check_root_candidate


def test_resolve_inside_root(ws, perms):
    assert perms.resolve(PathRef(root="Demo", path="Downloads/notes.txt")) == Path(os.path.realpath(ws / "Downloads" / "notes.txt"))
    assert perms.resolve(PathRef(root="demo")) == Path(os.path.realpath(ws))  # alias is case-insensitive


@pytest.mark.parametrize("bad", ["../secret.txt", "Downloads/../../x", "C:/Windows", "/etc/passwd", "~/x",
                                 "a\\..\\..\\b", "CON", "bad|name"])
def test_invalid_paths_rejected_by_schema(bad):
    with pytest.raises(ValidationError):
        PathRef(root="Demo", path=bad)


def test_unknown_root_rejected(perms):
    with pytest.raises(PathViolation):
        perms.resolve(PathRef(root="System32"))


def test_trash_not_directly_accessible(ws, perms):
    (ws / ".agent_trash").mkdir()
    with pytest.raises(PathViolation):
        perms.resolve(PathRef(root="Demo", path=".agent_trash"))


def _link_dir(link: Path, target: Path) -> bool:
    try:
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        else:
            os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, AttributeError):
        return False


def test_symlink_or_junction_escape_rejected(ws, perms, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    if not _link_dir(ws / "escape", outside):
        pytest.skip("cannot create a link on this system")
    with pytest.raises(PathViolation):
        perms.resolve(PathRef(root="Demo", path="escape/secret.txt"))


def test_read_only_root_blocks_writes(settings):
    settings.approved_roots[0].access = "read"
    p = Permissions(settings)
    p.resolve(PathRef(root="Demo", path="Downloads"))
    with pytest.raises(PathViolation):
        p.resolve(PathRef(root="Demo", path="Downloads"), write=True)


def test_to_ref_roundtrip(ws, perms):
    assert perms.to_ref(ws / "Photos" / "IMG_1.jpg") == PathRef(root="Demo", path="Photos/IMG_1.jpg")
    assert perms.to_ref(ws.parent) is None


def test_root_candidate_rules(ws, tmp_path, monkeypatch):
    import app.core.permissions as P
    assert any(P.is_within(ws, d) for d in P._system_dirs()) or check_root_candidate(str(ws))  # pytest tmp is in AppData
    with pytest.raises(PathViolation):  # ...and AppData itself is never approvable
        check_root_candidate(os.environ.get("LOCALAPPDATA") or "/etc")
    if os.name == "nt" and os.environ.get("SystemRoot"):
        with pytest.raises(PathViolation):
            check_root_candidate(os.environ["SystemRoot"])
    monkeypatch.setattr(P, "_system_dirs", lambda: [])
    assert check_root_candidate(str(ws)) == Path(os.path.realpath(ws))
    with pytest.raises(PathViolation):
        check_root_candidate(Path(ws.anchor).as_posix() if os.name != "nt" else ws.anchor)  # drive root
    with pytest.raises(PathViolation):
        check_root_candidate(str(Path.home()))
    with pytest.raises(PathViolation):
        check_root_candidate("relative/folder")
    with pytest.raises(PathViolation):
        check_root_candidate(str(tmp_path / "missing"))


def test_app_allowlist_lookup(perms):
    assert perms.find_app("notepad").name == "Notepad"
    assert perms.find_app("CALC").name == "Calculator"
    assert perms.find_app("powershell") is None

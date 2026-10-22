"""Folder creation, listing, rename, copy, move, collisions, quarantine, zip, duplicates — in temp dirs."""
from __future__ import annotations

import pytest

from app.actions import filesystem as fs
from app.actions import registry
from app.actions.registry import ConflictError, ExecContext
from app.core import action_schema as A
from app.core.action_schema import PathRef, StepStatus


def ctx(perms, settings, **kw):
    return ExecContext(perms=perms, settings=settings, **kw)


def test_create_folder_and_verify(ws, perms, settings):
    r = registry.execute(A.CreateFolder(target=PathRef(root="Demo", path="Projects/Reports")), ctx(perms, settings))
    assert r.status == StepStatus.SUCCESS and r.verified
    assert (ws / "Projects" / "Reports").is_dir()
    assert r.undo[0]["op"] == "remove_empty_dir"


def test_create_existing_folder_is_skipped(ws, perms, settings):
    r = registry.execute(A.CreateFolder(target=PathRef(root="Demo", path="Photos")), ctx(perms, settings))
    assert r.status == StepStatus.SKIPPED


def test_list_files_with_extension_filter_hides_trash(ws, perms, settings):
    (ws / "Downloads" / ".agent_trash").mkdir()
    r = registry.execute(A.ListFiles(target=PathRef(root="Demo", path="Downloads"), extensions=["txt"]),
                         ctx(perms, settings))
    names = sorted(x["name"] for x in r.details["rows"])
    assert names == ["notes.txt", "notes_copy.txt"]
    rows, _ = fs.list_entries(ws, recursive=True)
    assert not any(".agent_trash" in x["relative"] for x in rows)


def test_rename_file(ws, perms, settings):
    r = registry.execute(A.RenameFile(source=PathRef(root="Demo", path="Projects/roadmap.txt"), new_name="plan.txt"),
                         ctx(perms, settings))
    assert r.status == StepStatus.SUCCESS
    assert (ws / "Projects" / "plan.txt").exists() and not (ws / "Projects" / "roadmap.txt").exists()


def test_copy_verifies_content_and_keeps_original(ws, perms, settings):
    r = registry.execute(A.CopyFile(source=PathRef(root="Demo", path="Downloads/report.pdf"),
                                    destination=PathRef(root="Demo", path="Documents")), ctx(perms, settings))
    assert r.status == StepStatus.SUCCESS and r.verified
    assert (ws / "Documents" / "report.pdf").read_bytes() == (ws / "Downloads" / "report.pdf").read_bytes()


def test_move_file(ws, perms, settings):
    r = registry.execute(A.MoveFile(source=PathRef(root="Demo", path="Downloads/data.csv"),
                                    destination=PathRef(root="Demo", path="Documents")), ctx(perms, settings))
    assert r.status == StepStatus.SUCCESS
    assert (ws / "Documents" / "data.csv").exists() and not (ws / "Downloads" / "data.csv").exists()


@pytest.mark.parametrize("mode,expected", [("skip", StepStatus.SKIPPED), ("rename", StepStatus.SUCCESS)])
def test_collision_policies_never_overwrite(ws, perms, settings, mode, expected):
    (ws / "Documents" / "notes.txt").write_text("ORIGINAL", encoding="utf-8")
    r = registry.execute(A.CopyFile(source=PathRef(root="Demo", path="Downloads/notes.txt"),
                                    destination=PathRef(root="Demo", path="Documents")),
                         ctx(perms, settings, conflict_mode=mode))
    assert r.status == expected
    assert (ws / "Documents" / "notes.txt").read_text(encoding="utf-8") == "ORIGINAL"
    if mode == "rename":
        assert (ws / "Documents" / "notes (1).txt").read_text(encoding="utf-8") == "hello"


def test_collision_ask_raises_conflict(ws, perms, settings):
    (ws / "Documents" / "notes.txt").write_text("ORIGINAL", encoding="utf-8")
    with pytest.raises(ConflictError):
        registry.execute(A.MoveFile(source=PathRef(root="Demo", path="Downloads/notes.txt"),
                                    destination=PathRef(root="Demo", path="Documents")), ctx(perms, settings))
    assert (ws / "Downloads" / "notes.txt").exists()


def test_low_level_copy_refuses_overwrite(ws):
    with pytest.raises(FileExistsError):
        fs.copy_path(ws / "Downloads" / "notes.txt", ws / "Downloads" / "notes_copy.txt")


def test_delete_goes_to_quarantine_and_is_restorable(ws, perms, settings):
    r = registry.execute(A.DeleteFile(target=PathRef(root="Demo", path="Downloads/notes.txt")), ctx(perms, settings))
    assert r.status == StepStatus.SUCCESS
    assert not (ws / "Downloads" / "notes.txt").exists()
    trashed = list((ws / ".agent_trash").iterdir())
    assert len(trashed) == 1 and trashed[0].read_text(encoding="utf-8") == "hello"
    assert r.undo[0]["op"] == "restore"


def test_dry_run_changes_nothing(ws, perms, settings):
    r = registry.execute(A.MoveFile(source=PathRef(root="Demo", path="Downloads/data.csv"),
                                    destination=PathRef(root="Demo", path="Documents")),
                         ctx(perms, settings, dry_run=True))
    assert r.status == StepStatus.SIMULATED
    assert (ws / "Downloads" / "data.csv").exists() and not (ws / "Documents" / "data.csv").exists()


def test_write_text_file_never_overwrites(ws, perms, settings):
    a = A.WriteTextFile(target=PathRef(root="Demo", path="Projects/todo.txt"), content="Ship v1")
    assert registry.execute(a, ctx(perms, settings)).status == StepStatus.SUCCESS
    with pytest.raises(ConflictError):
        registry.execute(a, ctx(perms, settings))
    assert (ws / "Projects" / "todo.txt").read_text(encoding="utf-8") == "Ship v1"


def test_archive_and_duplicates(ws, perms, settings):
    r = registry.execute(A.ArchiveFolder(target=PathRef(root="Demo", path="Photos"),
                                         destination=PathRef(root="Demo", path="Photos.zip")), ctx(perms, settings))
    assert r.status == StepStatus.SUCCESS and fs.verify_zip(ws / "Photos.zip", 2)
    groups = fs.find_duplicates(ws / "Downloads")
    assert [sorted(p.name for p in g) for g in groups] == [["notes.txt", "notes_copy.txt"]]


def test_unique_path(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("x")
    assert fs.unique_path(p).name == "a (1).txt"

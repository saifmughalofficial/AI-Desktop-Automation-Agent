"""Strict action registry: one explicitly implemented handler per action type.

Each handler resolves paths through the sandbox, honours dry-run, refuses to
overwrite, performs exactly one registered operation, verifies the result and
returns undo information. Nothing here ever calls a shell."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.actions import app_launcher, filesystem as fs, pc_control, ui_automation
from app.config.settings import Settings
from app.core import action_schema as A
from app.core.action_schema import PathRef, StepStatus
from app.core.permissions import Permissions, PathViolation


class ConflictError(Exception):
    """Destination already exists and the conflict policy is 'ask'."""

    def __init__(self, target: str):
        super().__init__(f"'{target}' already exists. Choose: skip this item, keep both (auto-rename) or stop.")
        self.target = target


@dataclass
class ExecContext:
    perms: Permissions
    settings: Settings
    dry_run: bool = False
    conflict_mode: str = "ask"  # ask | skip | rename
    cancel: threading.Event | None = None
    launched: dict = field(default_factory=dict)  # app name (lower) -> {"pid", "handle"} or {"virtual": id}
    virtual: object | None = None  # VirtualDesktop in hosted mode


@dataclass
class ActionResult:
    status: StepStatus
    message: str
    verified: bool = False
    details: dict = field(default_factory=dict)
    undo: list[dict] = field(default_factory=list)


def _ok(msg, verified=True, **kw) -> ActionResult:
    return ActionResult(StepStatus.SUCCESS if verified else StepStatus.UNVERIFIED, msg, verified, **kw)


def _fail(msg) -> ActionResult:
    return ActionResult(StepStatus.FAILED, msg)


def _sim(msg) -> ActionResult:
    return ActionResult(StepStatus.SIMULATED, f"[dry run] {msg}", False)


def _ref(ctx: ExecContext, path: Path) -> dict | None:
    ref = ctx.perms.to_ref(path)
    return ref.model_dump() if ref else None


def _final_dest(dest: Path, ctx: ExecContext) -> Path | None:
    """Apply the conflict policy. Returns None to mean 'skip'."""
    if not dest.exists():
        return dest
    if ctx.conflict_mode == "rename":
        return fs.unique_path(dest)
    if ctx.conflict_mode == "skip":
        return None
    raise ConflictError(dest.name)


# --------------------------------------------------------------------------- read-only
def _list_files(a: A.ListFiles, ctx: ExecContext) -> ActionResult:
    folder = ctx.perms.resolve(a.target)
    if not folder.is_dir():
        return _fail(f"{a.target.display()} is not an existing folder.")
    rows, truncated = fs.list_entries(folder, extensions=a.extensions, pattern=a.name_pattern, recursive=a.recursive)
    files = [r for r in rows if r["kind"] == "file"]
    msg = (f"Found {len(files)} file(s) and {len(rows) - len(files)} folder(s) in {a.target.display()}"
           + (" (first 2000 shown)" if truncated else "") + ".")
    return _ok(msg, details={"rows": rows, "total_bytes": sum(r["size"] for r in files)})


def _find_duplicates(a: A.FindDuplicates, ctx: ExecContext) -> ActionResult:
    folder = ctx.perms.resolve(a.target)
    if not folder.is_dir():
        return _fail(f"{a.target.display()} is not an existing folder.")
    groups = fs.find_duplicates(folder, a.recursive)
    rows = []
    for gi, group in enumerate(groups, 1):
        for p in group:
            rows.append({"group": gi, "file": ctx.perms.to_ref(p).display(), "size_h": fs.human_size(p.stat().st_size)})
    msg = f"Found {len(groups)} group(s) of identical files in {a.target.display()}." if groups else \
        f"No duplicate files found in {a.target.display()}."
    return _ok(msg, details={"rows": rows})


# --------------------------------------------------------------------------- file changes
def _create_folder(a: A.CreateFolder, ctx: ExecContext) -> ActionResult:
    path = ctx.perms.resolve(a.target, write=True)
    if path.is_dir():
        return ActionResult(StepStatus.SKIPPED, f"{a.target.display()} already exists — nothing to do.", True)
    if path.exists():
        raise ConflictError(a.target.name)
    if not path.parent.is_dir():
        return _fail(f"Parent folder {a.target.parent.display()} does not exist.")
    if ctx.dry_run:
        return _sim(f"Would create folder {a.target.display()}.")
    fs.create_folder(path)
    if not path.is_dir():
        return _fail(f"Folder {a.target.display()} was not found after creation.")
    return _ok(f"Created folder {a.target.display()}.", undo=[{"op": "remove_empty_dir", "target": a.target.model_dump()}])


def _transfer(a, ctx: ExecContext, *, move: bool) -> ActionResult:
    verb = "Move" if move else "Copy"
    src = ctx.perms.resolve(a.source, write=move)
    dest_dir = ctx.perms.resolve(a.destination, write=True)
    if not src.exists():
        return _fail(f"Source {a.source.display()} no longer exists.")
    if not dest_dir.is_dir():
        return _fail(f"Destination folder {a.destination.display()} does not exist.")
    dest = _final_dest(dest_dir / (a.new_name or src.name), ctx)
    if dest is None:
        return ActionResult(StepStatus.SKIPPED, f"Skipped {a.source.display()}: a file with that name already exists "
                                                f"in {a.destination.display()}.", True)
    ctx.perms.resolve(ctx.perms.to_ref(dest), write=True)  # re-check final path inside the sandbox
    dest_ref = ctx.perms.to_ref(dest)
    if ctx.dry_run:
        return _sim(f"Would {verb.lower()} {a.source.display()} → {dest_ref.display()}.")
    if move:
        fs.move_path(src, dest)
        if dest.exists() and not src.exists():
            return _ok(f"Moved {a.source.display()} → {dest_ref.display()}.",
                       undo=[{"op": "move_back", "from": dest_ref.model_dump(), "to": a.source.model_dump()}])
        return _fail(f"Move could not be verified: destination exists={dest.exists()}, source still present={src.exists()}.")
    fs.copy_path(src, dest)
    if dest.exists() and fs.same_content(src, dest):
        digest = fs.sha256_file(dest) if dest.is_file() else None
        return _ok(f"Copied {a.source.display()} → {dest_ref.display()} (content verified).",
                   undo=[{"op": "quarantine_created", "target": dest_ref.model_dump(), "sha256": digest}])
    return _fail("Copy finished but the copy does not match the original.")


def _copy_file(a, ctx):
    return _transfer(a, ctx, move=False)


def _move_file(a, ctx):
    return _transfer(a, ctx, move=True)


def _rename_file(a: A.RenameFile, ctx: ExecContext) -> ActionResult:
    src = ctx.perms.resolve(a.source, write=True)
    if not src.exists():
        return _fail(f"{a.source.display()} no longer exists.")
    new_ref = a.source.parent.child(a.new_name)
    target = ctx.perms.resolve(new_ref, write=True)
    case_only = str(src).lower() == str(target).lower() and src.name != a.new_name
    if src.name == a.new_name:
        return ActionResult(StepStatus.SKIPPED, f"{a.source.display()} already has that name.", True)
    if not case_only:
        target = _final_dest(target, ctx)
        if target is None:
            return ActionResult(StepStatus.SKIPPED, f"Skipped: '{a.new_name}' already exists.", True)
    new_ref = ctx.perms.to_ref(target)
    if ctx.dry_run:
        return _sim(f"Would rename {a.source.display()} → {new_ref.name}.")
    fs.move_path(src, target)
    names = {p.name for p in target.parent.iterdir()}
    if target.name in names and (case_only or not src.exists()):
        return _ok(f"Renamed {a.source.display()} → {new_ref.name}.",
                   undo=[{"op": "move_back", "from": new_ref.model_dump(), "to": a.source.model_dump()}])
    return _fail("Rename could not be verified.")


def _delete_file(a: A.DeleteFile, ctx: ExecContext) -> ActionResult:
    path = ctx.perms.resolve(a.target, write=True)
    if not a.target.path:
        return _fail("An approved root folder cannot be deleted.")
    if not path.exists():
        return _fail(f"{a.target.display()} does not exist.")
    if ctx.dry_run:
        return _sim(f"Would move {a.target.display()} to the quarantine folder (.agent_trash).")
    trashed = fs.quarantine(path, ctx.perms.trash_dir(a.target.root))
    if not path.exists() and trashed.exists():
        trash_ref = PathRef(root=a.target.root, path=f".agent_trash/{trashed.name}")
        return _ok(f"Moved {a.target.display()} to quarantine (.agent_trash) — restorable with Undo.",
                   undo=[{"op": "restore", "from": trash_ref.model_dump(), "to": a.target.model_dump()}])
    return _fail("Delete (quarantine) could not be verified.")


def _write_text_file(a: A.WriteTextFile, ctx: ExecContext) -> ActionResult:
    path = ctx.perms.resolve(a.target, write=True)
    if not path.parent.is_dir():
        return _fail(f"Folder {a.target.parent.display()} does not exist.")
    path = _final_dest(path, ctx)
    if path is None:
        return ActionResult(StepStatus.SKIPPED, f"Skipped: {a.target.display()} already exists.", True)
    ref = ctx.perms.to_ref(path)
    if ctx.dry_run:
        return _sim(f"Would create {ref.display()} ({len(a.content)} characters).")
    fs.write_new_text(path, a.content)
    if path.read_text(encoding="utf-8") == a.content:
        return _ok(f"Created {ref.display()} ({len(a.content)} characters, read back and verified).",
                   undo=[{"op": "quarantine_created", "target": ref.model_dump(), "sha256": fs.sha256_file(path)}])
    return _fail("File was written but its content did not match on read-back.")


def _archive_folder(a: A.ArchiveFolder, ctx: ExecContext) -> ActionResult:
    folder = ctx.perms.resolve(a.target)
    dest = ctx.perms.resolve(a.destination, write=True)
    if not folder.is_dir():
        return _fail(f"{a.target.display()} is not a folder.")
    dest = _final_dest(dest, ctx)
    if dest is None:
        return ActionResult(StepStatus.SKIPPED, f"Skipped: {a.destination.display()} already exists.", True)
    ref = ctx.perms.to_ref(dest)
    if ctx.dry_run:
        return _sim(f"Would compress {a.target.display()} into {ref.display()}.")
    count = fs.make_zip(folder, dest)
    if fs.verify_zip(dest, count):
        return _ok(f"Created {ref.display()} with {count} file(s); ZIP integrity test passed.",
                   undo=[{"op": "quarantine_created", "target": ref.model_dump(), "sha256": fs.sha256_file(dest)}])
    return _fail("ZIP was written but failed the integrity test.")


# --------------------------------------------------------------------------- desktop
def _app_or_fail(ctx: ExecContext, name: str):
    app = ctx.perms.find_app(name)
    if not app:
        raise PathViolation(f"'{name}' is not on the application allowlist.")
    return app


def _launch_app(a: A.LaunchApp, ctx: ExecContext) -> ActionResult:
    app = _app_or_fail(ctx, a.app)
    if ctx.dry_run:
        return _sim(f"Would launch {app.name}.")
    if ctx.virtual is not None:
        win = ctx.virtual.open_app(app.name)
        ctx.launched[app.name.lower()] = {"virtual": win["id"]}
        ok = ctx.virtual.get(win["id"]) is not None
        return _ok(f"{app.name} opened in the web virtual desktop (window '{win['title']}' verified).", verified=ok,
                   details={"virtual": win["id"]})
    res = app_launcher.launch(app, timeout=ctx.settings.execution.verify_launch_timeout_s)
    if not res.ok:
        return _fail(res.message)
    ctx.launched[app.name.lower()] = {"pid": res.pid, "handle": res.handle}
    return _ok(res.message, verified=res.verified, details={"pid": res.pid, "handle": res.handle})


def _open_file(a: A.OpenFile, ctx: ExecContext) -> ActionResult:
    path = ctx.perms.resolve(a.target)
    if not path.is_file():
        return _fail(f"{a.target.display()} is not a file.")
    if ctx.dry_run:
        return _sim(f"Would open {a.target.display()} with its default application.")
    if ctx.virtual is not None:
        win = ctx.virtual.open_file(a.target.display(), path)
        return _ok(f"Opened {a.target.display()} in the web virtual desktop ({win['title']}).")
    res = app_launcher.open_with_default_app(path)
    return _ok(res.message, verified=res.verified) if res.ok else _fail(res.message)


def _open_folder(a: A.OpenFolder, ctx: ExecContext) -> ActionResult:
    path = ctx.perms.resolve(a.target)
    if not path.is_dir():
        return _fail(f"{a.target.display()} is not a folder.")
    if ctx.dry_run:
        return _sim(f"Would open {a.target.display()} in File Explorer.")
    if ctx.virtual is not None:
        rows, _ = fs.list_entries(path)
        ctx.virtual.open_folder(a.target.display(), rows)
        return _ok(f"Opened {a.target.display()} in the web File Explorer ({len(rows)} item(s)).")
    res = app_launcher.open_folder(path)
    return _ok(res.message, verified=res.verified) if res.ok else _fail(res.message)


def _inspect_ui(a: A.InspectUI, ctx: ExecContext) -> ActionResult:
    app = _app_or_fail(ctx, a.app)
    if ctx.virtual is not None:
        vid = (ctx.launched.get(app.name.lower()) or {}).get("virtual")
        win = ctx.virtual.get(vid) or ctx.virtual.latest(app.name.lower())
        if not win:
            return _fail(f"No {app.name} window is open in the web virtual desktop. Open it first.")
        rows = ctx.virtual.controls(win["id"])
        return _ok(f"Read {len(rows)} control(s) from the {app.name} web window (read-only).", details={"rows": rows})
    ok, why = ui_automation.available()
    if not ok:
        return _fail(why)
    handle = (ctx.launched.get(app.name.lower()) or {}).get("handle")
    try:
        rows = ui_automation.inspect_window(app.window_title, handle)
    except LookupError as exc:
        return _fail(str(exc))
    return _ok(f"Read {len(rows)} accessible control(s) from the {app.name} window (read-only).",
               details={"rows": rows})


def _type_text(a: A.TypeText, ctx: ExecContext) -> ActionResult:
    app = _app_or_fail(ctx, a.app)
    if ctx.virtual is not None:
        vid = (ctx.launched.get(app.name.lower()) or {}).get("virtual")
        if not ctx.virtual.get(vid):
            return _fail(f"For safety the agent only types into a {app.name} window it opened itself in this session, "
                         f"and none is open. Add 'open {app.name}' before this step.")
        if ctx.dry_run:
            return _sim(f"Would type {len(a.text)} characters into {app.name}.")
        verified, msg = ctx.virtual.type_text(vid, a.text)
        return _ok(f"{app.name} (web): {msg}", verified=verified)
    ok, why = ui_automation.available()
    if not ok:
        return _fail(why)
    info = ctx.launched.get(app.name.lower()) or {}
    handle = info.get("handle")
    if not handle or not ui_automation.window_exists(handle):
        return _fail(f"For safety the agent only types into a {app.name} window it opened itself in this session, "
                     f"and none is open. Add 'open {app.name}' before this step.")
    if ctx.dry_run:
        return _sim(f"Would type {len(a.text)} characters into {app.name}.")
    try:
        verified, msg = ui_automation.type_text(handle, a.text, ctx.settings.execution.verify_launch_timeout_s)
    except Exception as exc:  # UI automation is inherently fragile: stop safely, report honestly
        return _fail(f"UI automation could not control {app.name} reliably: {exc.__class__.__name__}: {exc}")
    return _ok(f"{app.name}: {msg}", verified=verified)


# --------------------------------------------------------------------------- web, programs, windows
def _open_url(a: A.OpenUrl, ctx: ExecContext) -> ActionResult:
    if ctx.dry_run:
        return _sim(f"Would open {a.url}" + ("" if a.browser == "default" else f" in {a.browser.title()}") + ".")
    if ctx.virtual is not None:
        win = ctx.virtual.open_link(a.url, a.url)
        return _ok(f"Ready in the web virtual desktop: click the link in “{win['title']}” to open {a.url}.")
    ok, msg = pc_control.open_url(a.url, a.browser)
    return _ok(msg, verified=False) if ok else _fail(msg)


def _compose_message(a: A.ComposeMessage, ctx: ExecContext) -> ActionResult:
    url = pc_control.compose_url(a.channel, a.to, a.subject, a.body)
    label = {"email": "email app", "gmail": "Gmail", "outlook": "Outlook", "whatsapp": "WhatsApp"}[a.channel]
    if ctx.dry_run:
        return _sim(f"Would open a pre-filled {label} draft ({len(a.body)} characters). Nothing is sent.")
    if ctx.virtual is not None:
        win = ctx.virtual.open_link(f"Draft — {label}", url, draft={"to": a.to, "subject": a.subject, "body": a.body})
        return _ok(f"Draft ready in “{win['title']}”: open it, review, and press Send yourself (the agent never sends).")
    ok, msg = pc_control.open_url(url) if a.channel != "email" else (app_launcher.open_mailto(url))
    return (_ok(f"Opened a pre-filled {label} draft — review it and press Send yourself. Nothing was sent.",
                verified=False) if ok else _fail(msg))


def _launch_program(a: A.LaunchProgram, ctx: ExecContext) -> ActionResult:
    if a.name not in pc_control.program_index():
        return _fail(f"{a.name} is not an installed Start-menu program.")
    if ctx.dry_run:
        return _sim(f"Would start {a.name}.")
    ok, verified, msg = pc_control.launch_program(a.name, ctx.settings.execution.verify_launch_timeout_s + 2)
    return _ok(msg, verified=verified) if ok else _fail(msg)


def _list_windows(a: A.ListWindows, ctx: ExecContext) -> ActionResult:
    if ctx.virtual is not None:
        rows = [{"title": w["title"], "process": "web window", "state": "open", "handle": w["id"]}
                for w in ctx.virtual.windows.values() if a.filter.lower() in w["title"].lower()]
    else:
        ok, why = ui_automation.available()
        if not ok:
            return _fail(why)
        rows = pc_control.list_windows(a.filter)
    return _ok(f"{len(rows)} open window(s)" + (f" matching '{a.filter}'" if a.filter else "") + ".",
               details={"rows": rows})


def _window_control(a: A.WindowControl, ctx: ExecContext) -> ActionResult:
    if ctx.virtual is not None:
        win = ctx.virtual.find(a.window)
        if not win:
            return _fail(f"No web window matches “{a.window}”.")
        if ctx.dry_run:
            return _sim(f"Would {a.op} “{win['title']}”.")
        if a.op == "close":
            ctx.virtual.close(win["id"])
            return _ok(f"Closed the web window “{win['title']}”.", verified=ctx.virtual.get(win["id"]) is None)
        return _ok(f"“{win['title']}” is shown in the web virtual desktop ({a.op} applies to real windows only).")
    ok, why = ui_automation.available()
    if not ok:
        return _fail(why)
    win, others = pc_control.find_window(a.window)
    if win is None:
        return _fail(f"No open window matches “{a.window}”." + (f" Open windows: {'; '.join(others)}." if others else ""))
    if ctx.dry_run:
        return _sim(f"Would {a.op} “{win.window_text()[:60]}”.")
    try:
        verified, msg = pc_control.window_op(win, a.op)
    except Exception as exc:  # UI automation is fragile: report honestly
        return _fail(f"Could not {a.op} the window: {exc.__class__.__name__}: {exc}")
    return _ok(msg, verified=verified)


def _browser_tab(a: A.BrowserTab, ctx: ExecContext) -> ActionResult:
    ok, why = ui_automation.available()
    if not ok:
        return _fail(why)
    if ctx.dry_run:
        return _sim(f"Would send '{a.op} tab' to the {a.browser} browser.")
    try:
        ok, msg = pc_control.browser_tab(a.op, a.browser)
    except Exception as exc:
        return _fail(f"Browser tab control failed: {exc.__class__.__name__}: {exc}")
    return _ok(msg, verified=False) if ok else _fail(msg)


def _take_screenshot(a: A.TakeScreenshot, ctx: ExecContext) -> ActionResult:
    from datetime import datetime
    folder = ctx.perms.resolve(a.destination, write=True)
    if not folder.is_dir():
        return _fail(f"{a.destination.display()} is not an existing folder.")
    dest = fs.unique_path(folder / f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png")
    ref = ctx.perms.to_ref(dest)
    if ctx.dry_run:
        return _sim(f"Would save a screenshot as {ref.display()}.")
    try:
        ok, msg = pc_control.screenshot(dest)
    except Exception as exc:
        return _fail(f"Screenshot failed: {exc}")
    if not ok:
        return _fail("The screenshot file could not be verified.")
    return _ok(f"{msg} → {ref.display()}", details={"image": str(dest)},
               undo=[{"op": "quarantine_created", "target": ref.model_dump(), "sha256": fs.sha256_file(dest)}])


HANDLERS: dict[str, Callable[..., ActionResult]] = {
    "list_files": _list_files, "find_duplicates": _find_duplicates, "create_folder": _create_folder,
    "copy_file": _copy_file, "move_file": _move_file, "rename_file": _rename_file, "delete_file": _delete_file,
    "write_text_file": _write_text_file, "archive_folder": _archive_folder, "launch_app": _launch_app,
    "open_file": _open_file, "open_folder": _open_folder, "inspect_ui": _inspect_ui, "type_text": _type_text,
    "open_url": _open_url, "compose_message": _compose_message, "launch_program": _launch_program,
    "list_windows": _list_windows, "window_control": _window_control, "browser_tab": _browser_tab,
    "take_screenshot": _take_screenshot,
}
assert set(HANDLERS) == set(A.ACTION_NAMES), "every schema action needs exactly one handler"


def execute(action, ctx: ExecContext) -> ActionResult:
    handler = HANDLERS.get(getattr(action, "action", None))
    if handler is None:
        return _fail("Unknown action — refused.")
    return handler(action, ctx)

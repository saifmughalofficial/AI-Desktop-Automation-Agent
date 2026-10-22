"""Planner: natural-language request -> reviewable, policy-checked Plan.

Pipeline: screen request (policy) -> parse (rules and/or optional local model)
-> expand macros into concrete actions -> describe each step -> policy
evaluation (risk, approval, conflicts, violations)."""
from __future__ import annotations

from pathlib import Path

from app.actions.filesystem import CATEGORIES, category_for
from app.config.settings import Settings
from app.core import action_schema as A
from app.core.action_schema import Plan, PlanStep, PathRef
from app.core.permissions import Permissions
from app.core.policy_engine import PolicyEngine
from app.core.workspace_index import WorkspaceIndex
from app.llm import rules_fallback as rules
from app.llm.local_model import LocalModelClient, ModelOutputError, ModelUnavailable

MAX_REQUEST = 2000


def describe(action) -> dict:
    """Plain-language description, expected result, verification and consequence for a step."""
    n = action.action
    if n == "list_files":
        what = (", ".join(f".{e}" for e in action.extensions) + " files") if action.extensions else "all items"
        if action.name_pattern:
            what = f"{what} matching '{action.name_pattern}'"
        return dict(description=f"List {what} in {action.target.display()}" + (" (including subfolders)" if action.recursive else ""),
                    expected="A table of matching files and folders.",
                    verification="Folder is read inside the approved root; listing returned.",
                    consequence="Read-only — nothing changes.")
    if n == "find_duplicates":
        return dict(description=f"Find identical files in {action.target.display()}",
                    expected="Groups of files with identical content (SHA-256).",
                    verification="Files compared by size, then by SHA-256 hash.",
                    consequence="Read-only — nothing is deleted.")
    if n == "create_folder":
        return dict(description=f"Create folder {action.target.display()}",
                    expected=f"An empty folder at {action.target.display()}.",
                    verification="Check that the folder exists after creation.",
                    consequence="Adds a new empty folder (Undo removes it if still empty).")
    if n in {"copy_file", "move_file"}:
        verb = "Copy" if n == "copy_file" else "Move"
        dest = f"{action.destination.display().rstrip('/')}/{action.new_name or action.source.name}"
        return dict(description=f"{verb} {action.source.display()} → {dest}",
                    expected=f"{action.source.name} present in {action.destination.display()}"
                             + (" and the original unchanged." if n == "copy_file" else " and no longer at its old path."),
                    verification="Compare size and SHA-256 of the copy with the original." if n == "copy_file"
                    else "Destination exists and the source path no longer exists.",
                    consequence="Creates a duplicate copy." if n == "copy_file"
                    else "The item is relocated; links to its old path will break (Undo moves it back).")
    if n == "rename_file":
        return dict(description=f"Rename {action.source.display()} → {action.new_name}",
                    expected=f"The item is named {action.new_name}.",
                    verification="New name exists and the old name is gone.",
                    consequence="The item's name changes (Undo restores it).")
    if n == "delete_file":
        return dict(description=f"Delete {action.target.display()} (move to quarantine)",
                    expected="The item is moved into the root's .agent_trash quarantine folder.",
                    verification="Original path is gone and the quarantined copy exists.",
                    consequence="The item disappears from its folder. It is NOT permanently erased — Undo restores it.")
    if n == "write_text_file":
        return dict(description=f"Create text file {action.target.display()} ({len(action.content)} characters)",
                    expected="A new UTF-8 text file. Existing files are never overwritten.",
                    verification="Read the file back and compare its contents.",
                    consequence="Adds a new file.")
    if n == "archive_folder":
        return dict(description=f"Compress {action.target.display()} → {action.destination.display()}",
                    expected="A new .zip archive containing the folder's files.",
                    verification="ZIP integrity test passes and the file count matches.",
                    consequence="Adds a new .zip file; the original folder is unchanged.")
    if n == "launch_app":
        return dict(description=f"Launch {action.app}",
                    expected=f"A new {action.app} window opens.",
                    verification="Wait for the application's window to appear (UI Automation).",
                    consequence="Opens an application window on your desktop.")
    if n == "open_file":
        return dict(description=f"Open {action.target.display()} with its default application",
                    expected="The file opens in its associated app.",
                    verification="Windows accepts the request (the app window itself cannot be verified).",
                    consequence="Opens a window; the file is not modified.")
    if n == "open_folder":
        return dict(description=f"Open {action.target.display()} in File Explorer",
                    expected="An Explorer window showing the folder.",
                    verification="Look for an Explorer window titled with the folder name.",
                    consequence="Opens a window; nothing changes.")
    if n == "inspect_ui":
        return dict(description=f"Inspect the accessible controls of the {action.app} window",
                    expected="A table of UI controls (type, name, automation id).",
                    verification="Window found via UI Automation and its controls enumerated.",
                    consequence="Read-only.")
    if n == "type_text":
        preview = action.text if len(action.text) <= 60 else action.text[:57] + "…"
        return dict(description=f"Type “{preview}” into the {action.app} window opened by the agent",
                    expected="The text appears at the end of the document.",
                    verification="Read the editor control back and confirm the text is present.",
                    consequence="Adds text to the window's unsaved document (nothing is saved to disk).")
    return dict(description=n, expected="", verification="", consequence="")


class Planner:
    def __init__(self, settings: Settings, perms: Permissions, policy: PolicyEngine,
                 llm: LocalModelClient | None = None):
        self.settings = settings
        self.perms = perms
        self.policy = policy
        self.llm = llm

    # ------------------------------------------------------------------ public
    def plan(self, request: str, *, selection: list[PathRef] | None = None, current: PathRef | None = None) -> Plan:
        text = (request or "").strip()
        plan = Plan(request=text)
        if not text:
            plan.clarification = "Type a task, e.g. 'list the files in Downloads'."
            return plan
        if len(text) > MAX_REQUEST:
            plan.blocked_reason = f"Requests are limited to {MAX_REQUEST} characters."
            return plan
        screen = self.policy.screen_request(text)
        if screen:
            plan.blocked_reason = screen.message
            plan.risk = screen.risk
            plan.summary = f"Refused ({screen.category.replace('_', ' ')})"
            return plan

        index = WorkspaceIndex(self.perms)
        ctx = rules.ParseContext(index=index, apps=self.perms.apps, workflows=self.settings.workflows,
                                 selection=list(selection or []), current=current)
        result, engine = self._parse(text, ctx, plan)
        plan.engine = engine
        plan.assumptions += result.assumptions
        plan.notes += result.notes
        plan.dry_run = result.dry_run
        if result.help:
            plan.help = True
            plan.summary = "Supported commands"
            return plan
        if result.clarification:
            plan.clarification, plan.clarification_kind = result.clarification, result.clarification_kind
            return plan

        try:
            actions = self._expand(result.items, index, ctx, plan, depth=0)
        except rules.NeedsClarification as q:
            plan.clarification, plan.clarification_kind = q.question, q.kind
            return plan
        if not actions:
            plan.clarification = plan.clarification or "Nothing to do: no files matched that request."
            return plan
        plan.steps = [PlanStep(index=i, action=a, **describe(a)) for i, a in enumerate(actions)]
        self.policy.evaluate(plan)
        self._finish(plan)
        return plan

    # ------------------------------------------------------------------ parsing
    def _parse(self, text: str, ctx: rules.ParseContext, plan: Plan):
        mode = self.settings.llm.mode
        if mode == "rules" or not self.llm:
            return rules.parse(text, ctx), "rules"
        if mode == "auto":
            # Hybrid: deterministic rules first; the local model only handles what the rules don't recognise.
            result = rules.parse(text, ctx)
            if not result.clarification:
                return result, "rules"
            if not self.llm.status().get("available"):
                if result.clarification == rules.UNKNOWN_MSG:
                    plan.notes.append("Tip: install Ollama and a small model to understand freer phrasing "
                                      "(Settings → Local AI). Currently using the rules-based parser.")
                return result, "rules"
            return self._model_parse(text, ctx, plan, fallback=result)
        return self._model_parse(text, ctx, plan, fallback=None)

    def _model_parse(self, text, ctx, plan, fallback):
        context = (f"Approved folder aliases: {', '.join(self.settings.root_aliases())}\n"
                   f"{ctx.index.summary_for_model()}\n"
                   f"Allowlisted apps: {', '.join(self.perms.app_names())}\n"
                   f"Selected files: {', '.join(s.display() for s in ctx.selection) or 'none'}")
        try:
            proposal, items, engine = self.llm.propose(text, context)
            res = rules.ParseResult(items=items, assumptions=list(proposal.assumptions), dry_run=proposal.dry_run,
                                    clarification=proposal.clarification)
            res.notes.append("Plan proposed by the local model and independently validated by the policy engine.")
            return res, engine
        except ModelUnavailable as exc:
            plan.notes.append(f"Local model unavailable ({exc}); used the rules-based parser instead.")
        except ModelOutputError as exc:
            plan.notes.append(f"Local model output was rejected ({exc}); used the rules-based parser instead.")
        return (fallback or rules.parse(text, ctx)), "rules"

    # ------------------------------------------------------------------ macro expansion
    def _expand(self, items, index: WorkspaceIndex, ctx, plan: Plan, depth: int) -> list:
        out: list = []
        for item in items:
            if not hasattr(item, "macro"):
                out.append(item)
                if isinstance(item, A.CreateFolder):
                    index.add_virtual_dir(item.target)
                continue
            m = item.macro
            if m == "organize_by_type":
                out += self._organize(item, index, plan)
            elif m == "bulk_rename":
                out += self._bulk_rename(item, index, plan)
            elif m == "bulk_transfer":
                files = item.files or index.files_in(item.source, item.extensions)
                if not files:
                    plan.notes.append(f"No matching files in {item.source.display() if item.source else 'the selection'}.")
                cls = A.CopyFile if item.operation == "copy" else A.MoveFile
                out += [cls(source=f, destination=item.destination) for f in files]
            elif m == "bulk_delete":
                files = item.files or index.files_in(item.target, item.extensions)
                if not files:
                    plan.notes.append("No matching files to delete.")
                out += [A.DeleteFile(target=f) for f in files]
            elif m == "run_workflow":
                if depth:
                    raise rules.NeedsClarification("Workflows cannot start other workflows.", "generic")
                wf = next((w for w in self.settings.workflows if w.name == item.name), None)
                if not wf:
                    raise rules.NeedsClarification(f"Workflow '{item.name}' no longer exists.", "generic")
                plan.notes.append(f"Workflow '{wf.name}': {len(wf.commands)} command(s).")
                for cmd in wf.commands:
                    sub = rules.parse(cmd, ctx)
                    if sub.clarification:
                        raise rules.NeedsClarification(f"Workflow step '{cmd}' needs attention: {sub.clarification}",
                                                       sub.clarification_kind)
                    plan.assumptions += sub.assumptions
                    plan.dry_run = plan.dry_run or sub.dry_run
                    out += self._expand(sub.items, index, ctx, plan, depth + 1)
        return out

    def _organize(self, item: A.OrganizeByType, index: WorkspaceIndex, plan: Plan) -> list:
        files = index.files_in(item.target)
        if not files:
            plan.notes.append(f"{item.target.display()} has no loose files to organize.")
            return []
        groups: dict[str, list[PathRef]] = {}
        for f in files:
            groups.setdefault(category_for(f.name), []).append(f)
        out: list = []
        order = list(CATEGORIES) + ["Other"]
        for cat in sorted(groups, key=order.index):
            dest = item.target.child(cat)
            if not index.is_dir(dest):
                out.append(A.CreateFolder(target=dest))
                index.add_virtual_dir(dest)
            out += [A.MoveFile(source=f, destination=dest) for f in groups[cat]]
        counts = ", ".join(f"{cat}: {len(v)}" for cat, v in groups.items())
        plan.expected_results.append(f"Files grouped by type in {item.target.display()} ({counts}).")
        return out

    def _bulk_rename(self, item: A.BulkRename, index: WorkspaceIndex, plan: Plan) -> list:
        files = list(item.files) or index.files_in(item.target, item.extensions)
        if item.files and item.extensions:
            files = [f for f in files if Path(f.name).suffix.lower().lstrip(".") in item.extensions] or files
        if not files:
            where = item.target.display() if item.target else "the selection"
            plan.notes.append(f"No matching files in {where} to rename.")
            return []
        out, skipped = [], 0
        for i, f in enumerate(sorted(files, key=lambda r: r.name.lower())):
            p = Path(f.name)
            if item.base_name:
                stem = f"{item.base_name}_{item.start + i:03d}"
            else:
                stem = p.stem
                if item.prefix and stem.startswith(item.prefix):
                    skipped += 1
                    continue
                stem = f"{item.prefix}{stem}{item.suffix}"
            out.append(A.RenameFile(source=f, new_name=f"{stem}{p.suffix}"))
        if skipped:
            plan.notes.append(f"{skipped} file(s) already had the prefix and were left unchanged.")
        return out

    # ------------------------------------------------------------------ wrap-up
    def _finish(self, plan: Plan) -> None:
        kinds: dict[str, int] = {}
        for s in plan.steps:
            kinds[s.action.action] = kinds.get(s.action.action, 0) + 1
        labels = {"list_files": "list", "find_duplicates": "duplicate scan", "create_folder": "create folder",
                  "copy_file": "copy", "move_file": "move", "rename_file": "rename", "delete_file": "delete",
                  "write_text_file": "create file", "archive_folder": "zip", "launch_app": "launch app",
                  "open_file": "open file", "open_folder": "open folder", "inspect_ui": "inspect UI",
                  "type_text": "type text"}
        parts = [f"{n}× {labels.get(k, k)}" for k, n in kinds.items()]
        plan.summary = f"{len(plan.steps)} action(s): " + ", ".join(parts)
        if plan.dry_run:
            plan.summary += " — preview only (dry run)"
        roots = sorted({t.split('/')[0] for s in plan.steps for t in s.targets if "/" in t})
        if roots:
            plan.preconditions.append(f"All file targets stay inside approved folder(s): {', '.join(roots)}.")
        if any(s.action.action in {"launch_app", "type_text", "inspect_ui"} for s in plan.steps):
            plan.preconditions.append("Applications must be on the allowlist; the agent runs visibly on your desktop.")
        if any(s.action.action in {"copy_file", "move_file", "rename_file", "write_text_file", "archive_folder"}
               for s in plan.steps):
            plan.preconditions.append("Existing files are never overwritten; name conflicts pause the run.")
        if not plan.expected_results:
            plan.expected_results = [s.expected for s in plan.steps[:3] if s.expected]
            if len(plan.steps) > 3:
                plan.expected_results.append(f"…and {len(plan.steps) - 3} more step(s).")

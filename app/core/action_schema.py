"""Typed action contract.

Every plan — whether produced by the rules parser or a local model — is parsed
into these models. Unknown action names, unexpected fields, absolute paths and
'..' traversal are rejected here, before the policy engine even sees them."""
from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator


class Risk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"

    @property
    def rank(self) -> int:
        return ["low", "medium", "high", "blocked"].index(self.value)


def max_risk(risks) -> Risk:
    risks = list(risks)
    return max(risks, key=lambda r: r.rank) if risks else Risk.LOW


_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_BAD_CHARS = set('<>:"|?*/\\') | {chr(i) for i in range(32)}
_EXT_RE = re.compile(r"^[a-z0-9]{1,8}$")


def validate_name(name: str) -> str:
    """A single file/folder name that is valid on Windows and cannot change directory."""
    n = (name or "").strip()
    if not n or n in {".", ".."}:
        raise ValueError("a file or folder name is required")
    if len(n) > 180:
        raise ValueError("name is too long (max 180 characters)")
    bad = sorted({c for c in n if c in _BAD_CHARS})
    if bad:
        raise ValueError(f"name {n!r} contains characters that are not allowed: {' '.join(map(repr, bad))}")
    if n.endswith((".", " ")):
        raise ValueError(f"name {n!r} must not end with a dot or a space")
    if n.split(".")[0].upper() in _RESERVED:
        raise ValueError(f"{n!r} is a reserved Windows device name")
    return n


def validate_relpath(path: str) -> str:
    """A path relative to an approved root, normalised to forward slashes."""
    p = (path or "").strip().replace("\\", "/")
    if p in {"", "."}:
        return ""
    if p.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", p):
        raise ValueError("absolute paths are not accepted; use a path relative to an approved folder")
    parts = [part for part in p.split("/") if part not in {"", "."}]
    for part in parts:
        if part == "..":
            raise ValueError("'..' path traversal is not allowed")
        validate_name(part)
    return "/".join(parts)


def normalize_extensions(exts) -> list[str]:
    out: list[str] = []
    for e in exts or []:
        e = str(e).strip().lower().lstrip("*").lstrip(".")
        if not _EXT_RE.match(e):
            raise ValueError(f"invalid file extension {e!r}")
        if e not in out:
            out.append(e)
    return out


class PathRef(BaseModel):
    """A location expressed as (approved-root alias, relative path) — never an absolute path."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    root: str = Field(min_length=1, max_length=40)
    path: str = ""

    @field_validator("path")
    @classmethod
    def _path(cls, v: str) -> str:
        return validate_relpath(v)

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1] if self.path else self.root

    @property
    def parent(self) -> "PathRef":
        return PathRef(root=self.root, path=self.path.rsplit("/", 1)[0] if "/" in self.path else "")

    def child(self, name: str) -> "PathRef":
        validate_name(name)
        return PathRef(root=self.root, path=f"{self.path}/{name}" if self.path else name)

    def display(self) -> str:
        return f"{self.root}/{self.path}" if self.path else f"{self.root}/"

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.display()


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _ext_list() -> Any:
    return Field(default_factory=list, max_length=40)


# --------------------------------------------------------------------------- actions
class ListFiles(_Strict):
    action: Literal["list_files"] = "list_files"
    target: PathRef
    extensions: list[str] = _ext_list()
    name_pattern: str | None = Field(None, max_length=120)
    recursive: bool = False

    @field_validator("extensions")
    @classmethod
    def check_exts(cls, v):
        return normalize_extensions(v)


class FindDuplicates(_Strict):
    action: Literal["find_duplicates"] = "find_duplicates"
    target: PathRef
    recursive: bool = True


class CreateFolder(_Strict):
    action: Literal["create_folder"] = "create_folder"
    target: PathRef

    @model_validator(mode="after")
    def _needs_name(self):
        if not self.target.path:
            raise ValueError("create_folder needs a folder name inside the approved folder")
        return self


class CopyFile(_Strict):
    action: Literal["copy_file"] = "copy_file"
    source: PathRef
    destination: PathRef  # destination folder
    new_name: str | None = None

    @field_validator("new_name")
    @classmethod
    def check_new_name(cls, v):
        return validate_name(v) if v else None


class MoveFile(_Strict):
    action: Literal["move_file"] = "move_file"
    source: PathRef
    destination: PathRef  # destination folder
    new_name: str | None = None

    @field_validator("new_name")
    @classmethod
    def check_new_name(cls, v):
        return validate_name(v) if v else None


class RenameFile(_Strict):
    action: Literal["rename_file"] = "rename_file"
    source: PathRef
    new_name: str

    @field_validator("new_name")
    @classmethod
    def check_new_name(cls, v):
        return validate_name(v)


class DeleteFile(_Strict):
    """'Delete' moves the item into the root's .agent_trash quarantine so it can be restored."""

    action: Literal["delete_file"] = "delete_file"
    target: PathRef


class WriteTextFile(_Strict):
    action: Literal["write_text_file"] = "write_text_file"
    target: PathRef
    content: str = Field("", max_length=20000)


class ArchiveFolder(_Strict):
    action: Literal["archive_folder"] = "archive_folder"
    target: PathRef
    destination: PathRef  # the .zip file to create


class LaunchApp(_Strict):
    action: Literal["launch_app"] = "launch_app"
    app: str = Field(min_length=1, max_length=60)


class OpenFile(_Strict):
    action: Literal["open_file"] = "open_file"
    target: PathRef


class OpenFolder(_Strict):
    action: Literal["open_folder"] = "open_folder"
    target: PathRef


class InspectUI(_Strict):
    action: Literal["inspect_ui"] = "inspect_ui"
    app: str = Field(min_length=1, max_length=60)


class TypeText(_Strict):
    action: Literal["type_text"] = "type_text"
    app: str = Field(min_length=1, max_length=60)
    text: str = Field(min_length=1, max_length=2000)


_EXEC_URL = re.compile(r"\.(exe|msi|bat|cmd|ps1|vbs|scr|jar|apk|dmg|com|hta)(?:$|[?#])", re.I)
_EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[a-z]{2,}$", re.I)


class OpenUrl(_Strict):
    """Open a web page (http/https only) in the default or a named browser."""
    action: Literal["open_url"] = "open_url"
    url: str = Field(min_length=8, max_length=2048)
    browser: Literal["default", "chrome", "edge", "firefox"] = "default"

    @field_validator("url")
    @classmethod
    def check_url(cls, v: str) -> str:
        from urllib.parse import urlsplit
        v = v.strip()
        if any(ord(c) < 33 for c in v):
            raise ValueError("URLs cannot contain spaces or control characters")
        u = urlsplit(v)
        if u.scheme.lower() not in {"http", "https"} or not u.hostname:
            raise ValueError("only http:// and https:// web addresses can be opened")
        if u.username or u.password:
            raise ValueError("URLs with embedded user names or passwords are refused")
        if _EXEC_URL.search(u.path or ""):
            raise ValueError("links that download programs or scripts are refused")
        return v


class ComposeMessage(_Strict):
    """Open a pre-filled draft (email / Gmail / Outlook / WhatsApp). The user reviews and sends it themselves."""
    action: Literal["compose_message"] = "compose_message"
    channel: Literal["email", "gmail", "outlook", "whatsapp"] = "email"
    to: str = Field("", max_length=300)
    subject: str = Field("", max_length=200)
    body: str = Field("", max_length=4000)

    @model_validator(mode="after")
    def _check(self):
        to = self.to.strip()
        if self.channel == "whatsapp":
            if to and not re.fullmatch(r"\+?[\d\s()-]{7,20}", to):
                raise ValueError("a WhatsApp recipient must be a phone number with country code, e.g. +923001234567")
        else:
            for addr in filter(None, (a.strip() for a in re.split(r"[;,]", to))):
                if not _EMAIL.match(addr):
                    raise ValueError(f"{addr!r} is not a valid email address")
        if not (self.body.strip() or self.subject.strip()):
            raise ValueError("a draft needs a message text")
        return self


class LaunchProgram(_Strict):
    """Start an installed program found in the Start menu (not on the allowlist, so it needs approval)."""
    action: Literal["launch_program"] = "launch_program"
    name: str = Field(min_length=1, max_length=100)


class ListWindows(_Strict):
    action: Literal["list_windows"] = "list_windows"
    filter: str = Field("", max_length=60)


class WindowControl(_Strict):
    action: Literal["window_control"] = "window_control"
    op: Literal["focus", "minimize", "maximize", "restore", "close"]
    window: str = Field(min_length=1, max_length=120)


class BrowserTab(_Strict):
    action: Literal["browser_tab"] = "browser_tab"
    op: Literal["new", "close", "next", "previous", "reload"]
    browser: Literal["any", "chrome", "edge", "firefox"] = "any"


class TakeScreenshot(_Strict):
    action: Literal["take_screenshot"] = "take_screenshot"
    destination: PathRef  # folder that receives screenshot_<timestamp>.png


Action = Annotated[
    Union[ListFiles, FindDuplicates, CreateFolder, CopyFile, MoveFile, RenameFile, DeleteFile,
          WriteTextFile, ArchiveFolder, LaunchApp, OpenFile, OpenFolder, InspectUI, TypeText, OpenUrl,
          ComposeMessage, LaunchProgram, ListWindows, WindowControl, BrowserTab, TakeScreenshot],
    Field(discriminator="action"),
]
ACTION_ADAPTER: TypeAdapter = TypeAdapter(Action)
ACTION_NAMES = ["list_files", "find_duplicates", "create_folder", "copy_file", "move_file", "rename_file",
                "delete_file", "write_text_file", "archive_folder", "launch_app", "open_file", "open_folder",
                "inspect_ui", "type_text", "open_url", "compose_message", "launch_program", "list_windows",
                "window_control", "browser_tab", "take_screenshot"]


# --------------------------------------------------------------------------- macros
# Macros are planner-level intents that expand into concrete, individually checked actions.
class OrganizeByType(_Strict):
    macro: Literal["organize_by_type"] = "organize_by_type"
    target: PathRef


class BulkRename(_Strict):
    macro: Literal["bulk_rename"] = "bulk_rename"
    target: PathRef | None = None
    files: list[PathRef] = Field(default_factory=list, max_length=500)
    extensions: list[str] = _ext_list()
    prefix: str = Field("", max_length=60)
    suffix: str = Field("", max_length=60)
    base_name: str | None = Field(None, max_length=80)
    start: int = Field(1, ge=0, le=100000)

    @field_validator("extensions")
    @classmethod
    def check_exts(cls, v):
        return normalize_extensions(v)

    @model_validator(mode="after")
    def _check(self):
        if not (self.prefix or self.suffix or self.base_name):
            raise ValueError("bulk_rename needs a prefix, suffix or base_name")
        for part in (self.prefix, self.suffix, self.base_name or ""):
            if part and any(c in _BAD_CHARS for c in part):
                raise ValueError(f"{part!r} contains characters that are not allowed in file names")
        if not self.target and not self.files:
            raise ValueError("bulk_rename needs a target folder or a list of files")
        return self


class BulkTransfer(_Strict):
    macro: Literal["bulk_transfer"] = "bulk_transfer"
    operation: Literal["copy", "move"]
    source: PathRef | None = None
    files: list[PathRef] = Field(default_factory=list, max_length=500)
    extensions: list[str] = _ext_list()
    destination: PathRef

    @field_validator("extensions")
    @classmethod
    def check_exts(cls, v):
        return normalize_extensions(v)

    @model_validator(mode="after")
    def _check(self):
        if not self.source and not self.files:
            raise ValueError("bulk_transfer needs a source folder or a list of files")
        return self


class BulkDelete(_Strict):
    macro: Literal["bulk_delete"] = "bulk_delete"
    target: PathRef | None = None
    files: list[PathRef] = Field(default_factory=list, max_length=500)
    extensions: list[str] = _ext_list()

    @field_validator("extensions")
    @classmethod
    def check_exts(cls, v):
        return normalize_extensions(v)

    @model_validator(mode="after")
    def _check(self):
        if not self.files and not (self.target and self.extensions):
            raise ValueError("bulk_delete needs explicit files, or a folder plus file types")
        return self


class RunWorkflow(_Strict):
    macro: Literal["run_workflow"] = "run_workflow"
    name: str = Field(min_length=1, max_length=60)


Macro = Annotated[Union[OrganizeByType, BulkRename, BulkTransfer, BulkDelete, RunWorkflow],
                  Field(discriminator="macro")]
MACRO_ADAPTER: TypeAdapter = TypeAdapter(Macro)


def parse_action(payload: Any):
    return ACTION_ADAPTER.validate_python(payload)


def parse_step_payload(payload: Any):
    """Validate one untrusted step (from a model or a file). Raises ValueError on anything unexpected."""
    if not isinstance(payload, dict):
        raise ValueError("each step must be a JSON object")
    if "macro" in payload and "action" in payload:
        raise ValueError("a step cannot be both an action and a macro")
    if "macro" in payload:
        return MACRO_ADAPTER.validate_python(payload)
    if "action" in payload:
        name = payload.get("action")
        if name not in ACTION_NAMES:
            raise ValueError(f"unknown action {name!r}; allowed: {', '.join(ACTION_NAMES)}")
        return ACTION_ADAPTER.validate_python(payload)
    raise ValueError("step has neither an 'action' nor a 'macro' field")


# --------------------------------------------------------------------------- plans
class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    UNVERIFIED = "unverified"
    SIMULATED = "simulated"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class PlanStep(BaseModel):
    index: int
    action: Action
    description: str
    targets: list[str] = Field(default_factory=list)
    risk: Risk = Risk.LOW
    requires_confirmation: bool = False
    expected: str = ""
    verification: str = ""
    consequence: str = ""
    preconditions: list[str] = Field(default_factory=list)
    conflict: str | None = None
    violation: str | None = None
    note: str | None = None


class Plan(BaseModel):
    request: str
    summary: str = ""
    engine: str = "rules"
    steps: list[PlanStep] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    expected_results: list[str] = Field(default_factory=list)
    clarification: str | None = None
    clarification_kind: str = "generic"
    blocked_reason: str | None = None
    help: bool = False
    dry_run: bool = False
    risk: Risk = Risk.LOW
    requires_approval: bool = False

    @property
    def violations(self) -> list[str]:
        return [f"Step {s.index + 1}: {s.violation}" for s in self.steps if s.violation]

    @property
    def conflicts(self) -> list[str]:
        return [f"Step {s.index + 1}: {s.conflict}" for s in self.steps if s.conflict]

    @property
    def executable(self) -> bool:
        return bool(self.steps) and not self.clarification and not self.blocked_reason and not self.violations

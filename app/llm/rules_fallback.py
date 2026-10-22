"""Transparent rules-based command parser — works with no AI model installed.

It recognises a documented set of phrasings (see the User Guide) and turns
them into typed actions/macros. When something is ambiguous it raises a
clarifying question instead of guessing. Its output is untrusted in the same
way a model's is: every step still goes through schema validation and the
policy engine."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.actions.filesystem import ARCHIVE_EXTS, AUDIO_EXTS, CODE_EXTS, DOC_EXTS, IMAGE_EXTS, KNOWN_EXTS, VIDEO_EXTS
from app.config.settings import AppEntry, Workflow
from app.core import action_schema as A
from app.core.action_schema import PathRef, validate_name
from app.core.workspace_index import WorkspaceIndex, norm

EXAMPLES = [
    "Create a folder named Reports in my Projects directory",
    "List the files in my Downloads folder",
    "Preview renaming the images in Photos using the prefix Event_",
    "Open Notepad",
    "Organize my files in Downloads by type, but show me the proposed changes first",
    "Copy all pdf files from Downloads to Documents",
    "Find duplicates in Demo",
    "Zip the Projects folder",
    "Create a text file named todo in Projects with text 'Ship v1.0'",
    "Type 'Hello from the agent' in Notepad",
    "Search for notes in Demo",
    "Run workflow Workspace Report",
    "Undo the last run",
]

UNKNOWN_MSG = ("I couldn't match that to a supported action. Try for example: 'list files in Downloads', "
               "'create a folder named Reports in Projects', 'copy all pdf files from Downloads to Documents', "
               "'open Notepad' — the Manual page lists every supported command.")


class NeedsClarification(Exception):
    def __init__(self, question: str, kind: str = "generic"):
        super().__init__(question)
        self.question = question
        self.kind = kind  # location | destination | source | name | generic


@dataclass
class ParseContext:
    index: WorkspaceIndex
    apps: list[AppEntry] = field(default_factory=list)
    workflows: list[Workflow] = field(default_factory=list)
    selection: list[PathRef] = field(default_factory=list)
    current: PathRef | None = None


@dataclass
class ParseResult:
    items: list = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    dry_run: bool = False
    clarification: str | None = None
    clarification_kind: str = "generic"
    help: bool = False
    last_ref: PathRef | None = None
    last_app: str | None = None


# --------------------------------------------------------------------------- vocabulary
_FILLER = re.compile(r"^(?:(?:hey|hi|ok|okay)\s+(?:agent\s*,?\s+)?)?(?:please\s+|kindly\s+|can you\s+|could you\s+|"
                     r"would you\s+|will you\s+|i want (?:you )?to\s+|i'?d like (?:you )?to\s+|i need (?:you )?to\s+|"
                     r"let'?s\s+|go ahead and\s+|now\s+|just\s+)+", re.I)
_TRAIL = re.compile(r"(?:\s*,?\s*(?:please|for me|thanks?(?: you)?|now|asap))+\s*[.!?]*\s*$", re.I)
_PREVIEW = re.compile(
    r"\b(?:preview(?:ing)?|dry[- ]?run|simulate|what would happen|"
    r"(?:show|tell|give) me (?:the |a )?(?:proposed |planned |suggested )?(?:changes|plan|layout|preview)(?: first)?|"
    r"(?:do not|don'?t|dont|without) (?:actually )?(?:move|change|rename|touch|copy|delete|modify|making changes|"
    r"changing)(?: anything)?(?: yet)?|suggest(?:ion)?s?|propose)\b", re.I)
_SPLIT = re.compile(r"\s*(?:;|\n|,?\s+and then\s+|,?\s+then\s+|,?\s+after that,?\s+|,?\s+afterwards,?\s+|"
                    r",?\s+and\s+(?=(?:open|launch|start|type|write|create|make|list|show|copy|move|rename|delete|"
                    r"find|search|zip|compress|organi[sz]e|sort|inspect)\b))\s*", re.I)
_QUOTE = re.compile(r"(?<![\w])(['\"])(.+?)\1(?![\w])")
_FOLDER_WORDS = r"(?:folder|directory|dir|workspace)"
_STOPS = (r"(?:to|into|from|in|inside|using|with|by|but|then|and|named|called|as|so|that|which|first|only|please|"
          r"without|sorted|recursively|including|for|where|if|of)")
_LOC_RE = re.compile(
    rf"\b(?P<prep>in|inside|within|under|from|to|into|at|on|of)\s+(?:(?:my|the|our|your|this|that)\s+)?"
    rf"(?P<loc>\"[^\"]+\"|'[^']+'|[^\s,;!?]+(?:\s+(?!{_STOPS}\b|{_FOLDER_WORDS}\b)[^\s,;!?]+)*?)"
    rf"(?:\s+{_FOLDER_WORDS})?(?=\s+{_STOPS}\b|\s*[,;!?]|\.(?:\s|$)|\s*$)", re.I)
_NAME_RE = re.compile(
    r"\b(?:named|called|titled|name it|call it)\s+(?P<v>\"[^\"]+\"|'[^']+'|.+?)"
    r"(?=\s+(?:in|inside|within|under|at|on|with|containing|saying|that|to|into|and|then)\b|\s*[,;!?]|\.(?:\s|$)|\s*$)",
    re.I)
_FILE_TOKEN = re.compile(r"(?<![\w/\\])(\"[^\"]+\.[A-Za-z0-9]{1,6}\"|'[^']+\.[A-Za-z0-9]{1,6}'|"
                         r"[\w\-()]+(?:\.[\w\-()]+)*\.[A-Za-z][A-Za-z0-9]{0,5})(?![\w])")
_SELECTION_WORDS = re.compile(r"\b(?:selected|selection|these|those|them|chosen|marked)\b", re.I)
_ALL_WORDS = re.compile(r"\b(?:all|every|everything|each|files)\b", re.I)
_TYPE_WORDS: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"\b(?:images?|photos?|pictures?|pics|screenshots?|graphics)\b", re.I), IMAGE_EXTS),
    (re.compile(r"\bpdfs?\b", re.I), ["pdf"]),
    (re.compile(r"\b(?:documents?|docs)\b", re.I), DOC_EXTS),
    (re.compile(r"\btext files?\b", re.I), ["txt", "md"]),
    (re.compile(r"\b(?:spreadsheets?|csv files?|excel files?)\b", re.I), ["csv", "xls", "xlsx", "ods"]),
    (re.compile(r"\b(?:archives?|zip files?|zips|compressed files?)\b", re.I), ARCHIVE_EXTS),
    (re.compile(r"\b(?:audio|music|songs?|sounds?)\b", re.I), AUDIO_EXTS),
    (re.compile(r"\b(?:videos?|movies?|clips?)\b", re.I), VIDEO_EXTS),
    (re.compile(r"\b(?:python files?|python scripts?)\b", re.I), ["py"]),
    (re.compile(r"\b(?:code files?|source files?|source code)\b", re.I), CODE_EXTS),
]
_BARE_EXT = re.compile(r"\b(pdf|jpe?g|png|gif|bmp|webp|txt|csv|docx?|xlsx?|pptx?|zip|mp3|mp4|wav|md|py|json|html)s?\b"
                       r"(?=\s+(?:files?|documents?|images?)\b|s\b)", re.I)
_GENERIC = re.compile(r"\b(?:the|my|our|all|files?|file names?|names?|and|extensions?|contents?|items?|everything|"
                      r"folders?|directory|directories|stuff|things|of|in|a|an|it|its|what'?s|what is|me|up|by type|"
                      r"by category|by extension|by kind|type|please)\b", re.I)
_LOC_PREPS = {"in", "inside", "within", "under", "from", "at", "on"}


@dataclass
class _Loc:
    prep: str
    phrase: str
    span: tuple[int, int]


def _unq(s: str) -> str:
    s = (s or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1].strip()
    return s.strip().rstrip(".,;:!?").strip()


def _locations(text: str, preps: set[str]) -> list[_Loc]:
    return [_Loc(m.group("prep").lower(), m.group("loc"), m.span()) for m in _LOC_RE.finditer(text)
            if m.group("prep").lower() in preps]


def _blank(text: str, spans) -> str:
    chars = list(text)
    for a, b in spans:
        chars[a:b] = " " * (b - a)
    return "".join(chars)


def _grab(pattern: str, text: str) -> tuple[str | None, tuple[int, int] | None]:
    m = re.search(pattern, text, re.I)
    if not m:
        return None, None
    return _unq(m.group("v")), m.span()


def _extensions(text: str) -> list[str]:
    exts: list[str] = []
    for pattern, lst in _TYPE_WORDS:
        if pattern.search(text):
            exts += lst
    for m in re.finditer(r"(?:^|[\s,(])\*?\.([A-Za-z0-9]{1,6})\b", text):
        exts.append(m.group(1).lower())
    for m in re.finditer(r"\b([A-Za-z0-9]{2,5})\s+files?\b", text):
        exts.append(m.group(1).lower())
    for m in _BARE_EXT.finditer(text):
        exts.append(m.group(1).lower())
    out: list[str] = []
    for e in exts:
        e = "jpeg" if e == "jpeg" else e
        if e in KNOWN_EXTS and e not in out:
            out.append(e)
    if "jpg" in out and "jpeg" not in out:
        out.append("jpeg")
    return out


def _match_app(text: str, apps: list[AppEntry]) -> AppEntry | None:
    t = re.sub(r"^(?:the|a|an|new|my)\s+", "", (text or "").strip().lower())
    t = re.sub(r"\s+(?:app|application|program|window)$", "", t).strip(" .")
    for app in apps:
        if app.matches(t) or norm(app.name) == norm(t):
            return app
    return None


# --------------------------------------------------------------------------- resolution helpers
def _aliases(ctx: ParseContext) -> str:
    return ", ".join(r.root for r in ctx.index.roots) or "none"


def _resolve_location(phrase: str, ctx: ParseContext) -> PathRef:
    p = _unq(phrase)
    p = re.sub(r"^(?:my|the|our|your)\s+", "", p, flags=re.I)
    p = re.sub(r"\s+(?:folder|directory|dir)$", "", p, flags=re.I).strip()
    if not p:
        raise NeedsClarification("Which folder do you mean?", "location")
    if ".." in p.replace("\\", "/").split("/") or re.match(r"^[A-Za-z]:|^[/\\~]", p):
        raise NeedsClarification(f"'{p}' is outside the sandbox. Only approved folders ({_aliases(ctx)}) and their "
                                 "subfolders can be used — absolute paths and '..' are refused.", "location")
    root = ctx.index.root_for(p)
    if root:
        return root
    if "/" in p or "\\" in p:
        head, _, tail = p.replace("\\", "/").partition("/")
        r = ctx.index.root_for(head)
        if r:
            try:
                ref = PathRef(root=r.root, path=tail)
            except ValidationError as exc:
                raise NeedsClarification(f"'{p}' is not a valid folder path: {exc.errors()[0]['msg']}", "location")
            if ctx.index.is_dir(ref):
                return ref
            raise NeedsClarification(f"Folder {ref.display()} does not exist.", "location")
    matches = ctx.index.find_dirs(p)
    if ctx.current and len(matches) > 1:
        under = [m for m in matches if m.root == ctx.current.root and m.path.startswith(ctx.current.path)]
        matches = under or matches
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        shown = ", ".join(m.display() for m in matches[:6])
        raise NeedsClarification(f"'{p}' matches several folders: {shown}. Which one? (e.g. '{matches[0].display()}')",
                                 "location")
    raise NeedsClarification(f"I can't find a folder called '{p}' inside the approved folders ({_aliases(ctx)}). "
                             "Add it in Settings → Approved folders, or name an existing folder.", "location")


def _default_location(ctx: ParseContext, res: ParseResult, purpose: str) -> PathRef:
    if ctx.current:
        res.assumptions.append(f"No folder was named, so I used the context folder {ctx.current.display()}.")
        return ctx.current
    if len(ctx.index.roots) == 1:
        root = ctx.index.roots[0]
        res.assumptions.append(f"No folder was named, so I used the only approved folder '{root.root}'.")
        return root
    raise NeedsClarification(f"Which approved folder should I use {purpose}? Options: {_aliases(ctx)}.", "location")


def _bare_target(text: str, ctx: ParseContext) -> PathRef | None:
    rest = _GENERIC.sub(" ", text)
    rest = re.sub(r"\s+", " ", rest).strip(" ,.;:'\"")
    return _resolve_location(rest, ctx) if rest else None


def _resolve_item(name: str, ctx: ParseContext, within: PathRef | None) -> PathRef:
    raw = _unq(name)
    if "/" in raw or "\\" in raw:
        head, _, tail = raw.replace("\\", "/").partition("/")
        r = ctx.index.root_for(head)
        try:
            ref = PathRef(root=r.root, path=tail) if r else (
                PathRef(root=within.root, path=f"{within.path}/{raw}".strip("/")) if within else None)
        except ValidationError as exc:
            raise NeedsClarification(f"'{raw}' is not a valid path: {exc.errors()[0]['msg']}", "generic")
        if ref and (ctx.index.is_dir(ref) or any(f == ref for f in ctx.index.files)):
            return ref
        raw = raw.replace("\\", "/").rsplit("/", 1)[-1]
    for sel in ctx.selection:
        if sel.name.lower() == raw.lower():
            return sel
    matches = ctx.index.find_files(raw, within)
    if not matches:
        matches = [d for d in ctx.index.find_dirs(raw)
                   if not within or (d.root == within.root and d.path.startswith(within.path))]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        shown = ", ".join(m.display() for m in matches[:6])
        raise NeedsClarification(f"Several items are named '{raw}': {shown}. Which one? Add 'in <folder>'.", "location")
    where = f" in {within.display()}" if within else " in the approved folders"
    raise NeedsClarification(f"I couldn't find '{raw}'{where}.", "generic")


def _selection(text: str, ctx: ParseContext, exts: list[str]) -> list[PathRef] | None:
    if not _SELECTION_WORDS.search(text):
        return None
    if not ctx.selection:
        return []
    if exts:
        return [s for s in ctx.selection if s.name.rsplit(".", 1)[-1].lower() in exts] or list(ctx.selection)
    return list(ctx.selection)


def _no_selection_error(what: str) -> NeedsClarification:
    return NeedsClarification(f"You referred to selected files, but nothing is selected. Select files in the "
                              f"File Explorer page, or name a folder for the {what} (e.g. 'in Photos').", "location")


# --------------------------------------------------------------------------- clause parsers
def _p_help(c, ctx, res):
    if re.match(r"^(?:help|\?|what can you do|commands|examples|how do i use (?:this|you)|what do you support)\b", c, re.I):
        res.help = True
        return []
    return None


def _p_workflow(c, ctx, res):
    m = re.match(r"^(?:run|start|execute|launch|play|do)\s+(?:the\s+|my\s+)?(?:workflow|routine)\s+(?P<n>.+)$", c, re.I) \
        or re.match(r"^(?:run|start|play|do)\s+(?:the\s+|my\s+)?(?P<n>.+?)\s+(?:workflow|routine)$", c, re.I)
    if not m:
        return None
    want = norm(_unq(m.group("n")))
    for wf in ctx.workflows:
        if norm(wf.name) == want:
            return [A.RunWorkflow(name=wf.name)]
    names = ", ".join(w.name for w in ctx.workflows) or "none defined"
    raise NeedsClarification(f"There is no workflow named '{_unq(m.group('n'))}'. Available: {names}.", "generic")


def _p_type_text(c, ctx, res):
    m = re.search(r"\b(?:type|write|enter|put)\s+(?P<q>['\"])(?P<text>.+?)(?P=q)"
                  r"(?:\s+(?:in|into|on)\s+(?:a\s+|the\s+|new\s+)*(?P<app>[\w .]+?)(?:\s+(?:window|app))?)?$", c, re.I)
    if not m:
        return None
    app_phrase = (m.group("app") or "").strip()
    if re.search(r"\bfile\b|\.\w{1,5}$|\bnamed\b", app_phrase, re.I):
        return None  # "write 'x' in a file named ..." is a text-file request
    if app_phrase:
        app = _match_app(app_phrase, ctx.apps)
        name = app.name if app else app_phrase
    elif res.last_app:
        name = res.last_app
    else:
        raise NeedsClarification("Which application should I type into? e.g. \"type 'hello' in Notepad\".", "generic")
    items = [] if res.last_app and res.last_app.lower() == name.lower() else [A.LaunchApp(app=name)]
    if items:
        res.assumptions.append(f"A new {name} window will be opened first — the agent only types into windows it opened.")
    res.last_app = name
    return items + [A.TypeText(app=name, text=m.group("text"))]


def _p_inspect(c, ctx, res):
    m = re.search(r"\b(?:inspect|analy[sz]e|scan|show|list|read)\b.*?\b(?:controls?|ui|elements?|buttons|"
                  r"accessibility tree|widgets)\b(?:\s+(?:of|in|for|on))?\s+(?:the\s+)?(?P<app>[\w .]+?)(?:\s+window)?$",
                  c, re.I) or re.match(r"^inspect\s+(?:the\s+)?(?P<app>[\w .]+?)(?:\s+(?:window|app|ui))?$", c, re.I)
    if not m:
        return None
    app = _match_app(m.group("app"), ctx.apps)
    return [A.InspectUI(app=app.name if app else m.group("app").strip())]


def _p_organize(c, ctx, res):
    if not re.search(r"\b(?:organi[sz]e|sort|tidy(?: up)?|clean ?up|arrange|categori[sz]e|group)\b|"
                     r"^\s*folders? for (?:the |my |these |all )?files\b", c, re.I):
        return None
    locs = _locations(c, _LOC_PREPS)
    if locs:
        target = _resolve_location(locs[0].phrase, ctx)
    else:
        m = re.search(r"\b(?:organi[sz]e|sort|tidy(?: up)?|clean ?up|arrange|categori[sz]e|group)\s+(?P<x>.+?)"
                      r"(?:\s+by\b.*)?$", c, re.I)
        target = (_bare_target(m.group("x"), ctx) if m else None) or _default_location(ctx, res, "to organize")
    return [A.OrganizeByType(target=target)]


def _p_duplicates(c, ctx, res):
    if not re.search(r"\bduplicat(?:e|es|ed)\b|\bidentical files\b|\bsame files\b", c, re.I):
        return None
    locs = _locations(c, _LOC_PREPS)
    target = _resolve_location(locs[0].phrase, ctx) if locs else _default_location(ctx, res, "to scan")
    return [A.FindDuplicates(target=target, recursive=True)]


def _p_archive(c, ctx, res):
    m = re.match(r"^(?:zip|compress|archive|back ?up)\s+(?:up\s+)?(?P<x>.+)$", c, re.I)
    if not m:
        return None
    rest = m.group("x")
    zip_name, span = _grab(r"\b(?:as|into|to)\s+(?P<v>\"[^\"]+\"|'[^']+'|[\w\-. ()]+?\.zip)\b", rest)
    if span:
        rest = _blank(rest, [span])
    locs = _locations(rest, _LOC_PREPS)
    target = _resolve_location(locs[0].phrase, ctx) if locs else _bare_target(rest, ctx)
    if not target:
        raise NeedsClarification("Which folder should I compress? e.g. 'zip the Projects folder'.", "location")
    if target.path:
        dest = target.parent.child(validate_name(zip_name or f"{target.name}.zip"))
    else:
        dest = target.child(validate_name(zip_name or f"{target.root}_archive.zip"))
    res.last_ref = dest
    return [A.ArchiveFolder(target=target, destination=dest)]


def _p_rename(c, ctx, res):
    if not re.search(r"\brenam(?:e|ing)\b", c, re.I):
        return None
    spans = []
    val = r"(?P<v>\"[^\"]+\"|'[^']+'|\S+)"
    prefix, sp = _grab(rf"\bprefix(?:ed)?\s+(?:of\s+|with\s+|to\s+)?{val}", c)
    spans += [sp] if sp else []
    suffix, sp = _grab(rf"\bsuffix(?:ed)?\s+(?:of\s+|with\s+|to\s+)?{val}", c)
    spans += [sp] if sp else []
    base, sp = _grab(r"\b(?:to|as)\s+(?P<v>\"[^\"]+\"|'[^']+'|[\w\-]+)\s+(?:with\s+|using\s+)?(?:sequential\s+|running\s+)?"
                     r"(?:numbers?|numbering|numbered|in sequence|sequentially)\b", c)
    spans += [sp] if sp else []
    if prefix or suffix or base:
        rest = _blank(c, spans)
        locs = _locations(rest, _LOC_PREPS)
        rest_wo = _blank(rest, [l.span for l in locs])
        exts = _extensions(rest_wo)
        try:
            macro_kw = dict(prefix=prefix or "", suffix=suffix or "", base_name=base, extensions=exts)
            sel = _selection(rest_wo, ctx, exts)
            if sel:
                return [A.BulkRename(files=sel, **macro_kw)]
            if locs:
                return [A.BulkRename(target=_resolve_location(locs[0].phrase, ctx), **macro_kw)]
            if sel == [] and not ctx.current:
                raise _no_selection_error("rename")
            if ctx.current:
                res.assumptions.append(f"No folder was named, so I used the context folder {ctx.current.display()}.")
                return [A.BulkRename(target=ctx.current, **macro_kw)]
        except ValidationError as exc:
            raise NeedsClarification(f"That rename pattern is not valid: {exc.errors()[0]['msg']}", "generic")
        raise NeedsClarification("Which files should I rename? Select them in File Explorer, or name a folder "
                                 "(e.g. 'in Photos').", "location")
    locs = _locations(c, {"in", "inside", "within", "from", "under"})
    rest = _blank(c, [l.span for l in locs])
    m = re.search(r"\brenam(?:e|ing)\s+(?:the\s+)?(?:file\s+|folder\s+)?(?P<src>\"[^\"]+\"|'[^']+'|.+?)\s+(?:to|as|into)\s+"
                  r"(?P<new>\"[^\"]+\"|'[^']+'|.+?)\s*$", rest, re.I)
    if not m:
        raise NeedsClarification("Tell me the current and the new name, e.g. 'rename notes.txt to notes_old.txt', or "
                                 "use 'rename the images in Photos using the prefix Event_'.", "generic")
    within = _resolve_location(locs[0].phrase, ctx) if locs else None
    src = _resolve_item(m.group("src"), ctx, within)
    new = _unq(m.group("new"))
    if "." in src.name and "." not in new and not ctx.index.is_dir(src):
        new += "." + src.name.rsplit(".", 1)[-1]
        res.assumptions.append(f"Kept the original extension: new name will be '{new}'.")
    try:
        validate_name(new)
    except ValueError as exc:
        raise NeedsClarification(f"'{new}' can't be used as a name: {exc}", "generic")
    res.last_ref = src.parent.child(new)
    return [A.RenameFile(source=src, new_name=new)]


def _subject_items(c: str, verb_re: str, ctx: ParseContext, res: ParseResult, *, source: PathRef | None,
                   what: str) -> tuple[list[PathRef] | None, list[str], PathRef | None]:
    """Work out which files a copy/move/delete refers to. Returns (explicit_items, extensions, source_folder)."""
    m = re.search(verb_re, c, re.I)
    subject = c[m.end():] if m else c
    exts = _extensions(subject)
    sel = _selection(subject, ctx, exts)
    if sel:
        return sel, exts, source
    names = [n for n in _FILE_TOKEN.findall(subject)]
    if names:
        return [_resolve_item(n, ctx, source) for n in names], exts, source
    if sel == [] and not source:
        raise _no_selection_error(what)
    leftover = re.sub(r"\s+", " ", _GENERIC.sub(" ", subject)).strip(" ,.;:")
    if leftover and not _ALL_WORDS.search(subject) and (
            ctx.index.find_files(leftover, source) or ctx.index.find_dirs(leftover)):
        return [_resolve_item(leftover, ctx, source)], [], source  # "delete Archive" = the item, not a file type
    if exts or _ALL_WORDS.search(subject):
        if not source:
            if ctx.current:
                res.assumptions.append(f"No source folder was named, so I used {ctx.current.display()}.")
                source = ctx.current
            else:
                raise NeedsClarification(f"From which folder should I {what} them? e.g. 'from Downloads'.", "source")
        return None, exts, source
    leftover = _GENERIC.sub(" ", subject)
    leftover = re.sub(r"\s+", " ", leftover).strip(" ,.;:")
    if leftover:
        return [_resolve_item(leftover, ctx, source)], exts, source
    raise NeedsClarification(f"Which files should I {what}? Name them, select them in File Explorer, or say e.g. "
                             f"'all pdf files from Downloads'.", "generic")


def _p_transfer(c, ctx, res):
    m = re.search(r"\b(copy|move|transfer|relocate)\b", c, re.I)
    if not m:
        return None
    op = "copy" if m.group(1).lower() == "copy" else "move"
    new_name, span = _grab(r"\s+as\s+(?P<v>\"[^\"]+\"|'[^']+'|\S+)\s*$", c)
    work = _blank(c, [span]) if span else c
    src_locs = _locations(work, {"from", "in", "inside", "within", "under"})
    dst_locs = _locations(work, {"to", "into"})
    if not dst_locs:
        raise NeedsClarification(f"Where should I {op} them? Name a destination folder, e.g. 'to Documents'.",
                                 "destination")
    dest = _resolve_location(dst_locs[-1].phrase, ctx)
    source = _resolve_location(src_locs[0].phrase, ctx) if src_locs else None
    rest = _blank(work, [l.span for l in src_locs + dst_locs])
    items, exts, source = _subject_items(rest, r"\b(?:copy|move|transfer|relocate)\b", ctx, res, source=source, what=op)
    if items is not None and len(items) == 1:
        cls = A.CopyFile if op == "copy" else A.MoveFile
        return [cls(source=items[0], destination=dest, new_name=new_name)]
    if new_name:
        res.notes.append("A new name ('as ...') only applies when a single file is copied or moved; it was ignored.")
    if items:
        return [A.BulkTransfer(operation=op, files=items, destination=dest)]
    return [A.BulkTransfer(operation=op, source=source, extensions=exts, destination=dest)]


def _p_delete(c, ctx, res):
    m = re.search(r"\b(delete|remove|trash|erase|discard|bin)\b", c, re.I)
    if not m:
        return None
    locs = _locations(c, _LOC_PREPS)
    source = _resolve_location(locs[0].phrase, ctx) if locs else None
    rest = _blank(c, [l.span for l in locs])
    items, exts, source = _subject_items(rest, r"\b(?:delete|remove|trash|erase|discard|bin)\b", ctx, res,
                                         source=source, what="delete")
    if items is not None:
        return [A.DeleteFile(target=i) for i in items] if len(items) == 1 else [A.BulkDelete(files=items)]
    if not exts:
        raise NeedsClarification("For safety, bulk deletes need a file type (e.g. 'delete the tmp files in Downloads') "
                                 "or explicitly selected files.", "generic")
    return [A.BulkDelete(target=source, extensions=exts)]


def _p_search(c, ctx, res):
    m = re.match(r"^(?:find|search(?: for)?|locate|look for|where(?:'s| is| are))\s+(?P<x>.+)$", c, re.I)
    if not m:
        return None
    x = m.group("x")
    locs = _locations(x, _LOC_PREPS)
    x_wo = _blank(x, [l.span for l in locs])
    term = None
    q = re.search(r"(['\"])(.+?)\1", x_wo)
    if q:
        term = q.group(2)
    else:
        t = re.sub(r"\b(?:all|the|my|any|files?|documents?|named|called|matching|containing|with|that|have|has|"
                   r"in (?:the )?name)\b", " ", x_wo, flags=re.I)
        term = re.sub(r"\s+", " ", t).strip(" ,.;:")
    exts = _extensions(x_wo)
    if exts and term and (term.lower().rstrip("s") in {"pdf", "image", "photo", "picture", "document", "doc",
                                                        "spreadsheet", "video", "audio", "music", "archive", "zip"}
                          or term.lower() in exts):
        term = ""
    pattern = None
    if term:
        pattern = term if any(ch in term for ch in "*?") else f"*{term}*"
    if not pattern and not exts:
        raise NeedsClarification("What should I search for? e.g. \"search for 'invoice' in Downloads\".", "generic")
    targets = [_resolve_location(locs[0].phrase, ctx)] if locs else list(ctx.index.roots)
    if not locs and len(targets) > 1:
        res.notes.append("No folder was named, so every approved folder is searched.")
    return [A.ListFiles(target=t, name_pattern=pattern, extensions=exts, recursive=True) for t in targets]


def _p_open(c, ctx, res):
    m = re.match(r"^(?:open|launch|start|run|fire up|bring up|load)\s+(?:up\s+)?(?:the\s+|my\s+|a\s+|an\s+|new\s+)*"
                 r"(?P<what>.+?)$", c, re.I)
    if not m:
        return None
    what = m.group("what").strip()
    explorer = bool(re.search(r"\s+(?:in|with)\s+(?:file\s+|windows\s+)?explorer$", what, re.I))
    what = re.sub(r"\s+(?:in|with)\s+(?:file\s+|windows\s+)?explorer$", "", what, flags=re.I)
    if what.lower() in {"it", "that", "that folder", "the folder", "this folder", "that file", "the file"}:
        if not res.last_ref:
            raise NeedsClarification("Open what? Name an app, file or folder.", "generic")
        ref = res.last_ref
        if ref.name.lower().endswith(tuple(f".{e}" for e in KNOWN_EXTS)) or "." in ref.name:
            return [A.OpenFile(target=ref)]
        return [A.OpenFolder(target=ref)]
    app = None if explorer else _match_app(what, ctx.apps)
    if app:
        res.last_app = app.name
        return [A.LaunchApp(app=app.name)]
    locs = _locations(what, _LOC_PREPS)
    within = _resolve_location(locs[0].phrase, ctx) if locs else None
    what_wo = _blank(what, [l.span for l in locs]).strip()
    tokens = _FILE_TOKEN.findall(what_wo)
    if tokens:
        return [A.OpenFile(target=_resolve_item(tokens[0], ctx, within))]
    folder_phrase = re.sub(r"\s+(?:folder|directory|dir)$", "", what_wo, flags=re.I).strip()
    if folder_phrase:
        try:
            return [A.OpenFolder(target=_resolve_location(folder_phrase, ctx))]
        except NeedsClarification:
            pass
    elif within:
        return [A.OpenFolder(target=within)]
    apps = ", ".join(a.name for a in ctx.apps) or "none"
    raise NeedsClarification(f"'{what}' isn't an allowlisted application or a file/folder I can find. Allowlisted "
                             f"apps: {apps}. More can be added in Settings → Applications.", "generic")


def _p_create_file(c, ctx, res):
    if not re.search(r"\b(?:create|make|write|new|add|save|start)\b", c, re.I):
        return None
    if not re.search(r"\b(?:text file|txt file|note|notes file|file|document|memo|to-?do list|markdown file)\b", c, re.I):
        return None
    if re.search(r"\bfolders?\b|\bdirector", c, re.I):
        return None
    content, span = _grab(r"\b(?:with|containing|saying|that says|reading)\s+(?:the\s+)?(?:text|content|contents|words?)?"
                          r"\s*:?\s*(?P<v>\"[^\"]*\"|'[^']*')", c)
    if content is None:
        content, span = _grab(r"\b(?:with (?:the )?(?:text|content)|saying|containing)\s*:?\s+(?P<v>.+)$", c)
    work = _blank(c, [span]) if span else c
    name, nspan = _grab(_NAME_RE.pattern, work)
    if not name:
        tokens = _FILE_TOKEN.findall(work)
        name = _unq(tokens[0]) if tokens else None
    if nspan:
        work = _blank(work, [nspan])
    if not name:
        raise NeedsClarification("What should the new text file be called?", "name")
    if "." not in name:
        name += ".txt"
    locs = _locations(work, {"in", "inside", "within", "under", "at", "to", "into"})
    folder = _resolve_location(locs[0].phrase, ctx) if locs else _default_location(ctx, res, "for the new file")
    try:
        target = folder.child(validate_name(name))
    except ValueError as exc:
        raise NeedsClarification(f"'{name}' can't be used as a file name: {exc}", "name")
    res.last_ref = target
    return [A.WriteTextFile(target=target, content=content or "")]


def _p_create_folder(c, ctx, res):
    if not re.search(r"\b(?:create|make|add|new|set ?up|build|prepare)\b", c, re.I):
        return None
    if not re.search(r"\b(?:folders?|director(?:y|ies)|subfolders?)\b", c, re.I):
        return None
    locs = _locations(c, {"in", "inside", "within", "under", "at", "on"})
    rest = _blank(c, [l.span for l in locs])
    raw, _ = _grab(_NAME_RE.pattern, rest)
    if not raw:
        m = re.search(r"\b(?:folders?|director(?:y|ies)|subfolders?)\s+(?:named\s+|called\s+)?(?P<n>.+)$", rest, re.I)
        raw = m.group("n").strip() if m else ""
        raw = re.sub(r"\s+(?:folders?|directory)$", "", raw, flags=re.I).strip(" .,")
    q = re.fullmatch(r"(['\"])(.+)\1", raw.strip())
    names = [q.group(2)] if q else [_unq(n) for n in re.split(r"\s*,\s*(?:and\s+)?|\s+and\s+", raw) if _unq(n)]
    if not names:
        raise NeedsClarification("What should the new folder be called?", "name")
    parent = _resolve_location(locs[0].phrase, ctx) if locs else _default_location(ctx, res, "for the new folder")
    items = []
    for name in names:
        cur = parent
        segments = [s for s in name.replace("\\", "/").split("/") if s.strip()]
        for i, seg in enumerate(segments):
            try:
                cur = cur.child(validate_name(seg))
            except ValueError as exc:
                raise NeedsClarification(f"'{seg}' can't be used as a folder name: {exc}", "name")
            # intermediate folders only when missing; the final one always (policy reports "already exists")
            is_last = i == len(segments) - 1
            if (is_last or not ctx.index.is_dir(cur)) and not any(
                    isinstance(it, A.CreateFolder) and it.target == cur for it in items):
                items.append(A.CreateFolder(target=cur))
            ctx.index.add_virtual_dir(cur)
        res.last_ref = cur
    return items


def _p_list(c, ctx, res):
    if not re.search(r"\b(?:list|show|display|view|see|browse|what(?:'s| is| are)?(?: files are)? in|contents? of|"
                     r"tell me what'?s in|check|inventory)\b", c, re.I):
        return None
    locs = _locations(c, _LOC_PREPS | {"of"})
    rest = _blank(c, [l.span for l in locs])
    exts = _extensions(rest)
    recursive = bool(re.search(r"\b(?:recursive(?:ly)?|all subfolders|including subfolders|subfolders too|"
                               r"everything under|deep)\b", c, re.I))
    if locs:
        target = _resolve_location(locs[0].phrase, ctx)
    else:
        m = re.search(r"\b(?:list|show|display|view|see|browse|check|inventory)\s+(?P<x>.+)$", rest, re.I)
        x = m.group("x") if m else ""
        for pattern, _ in _TYPE_WORDS:
            x = pattern.sub(" ", x)
        x = _BARE_EXT.sub(" ", x)
        x = re.sub(r"\b(?:recursive(?:ly)?|all subfolders|including subfolders|me)\b", " ", x, flags=re.I)
        target = _bare_target(x, ctx) or _default_location(ctx, res, "to list")
    return [A.ListFiles(target=target, extensions=exts, recursive=recursive)]


_PARSERS = [_p_help, _p_workflow, _p_type_text, _p_inspect, _p_organize, _p_duplicates, _p_archive, _p_rename,
            _p_transfer, _p_delete, _p_search, _p_open, _p_create_file, _p_create_folder, _p_list]


def _protect_quotes(text: str) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}

    def repl(m):
        key = f"\x00{len(mapping)}\x00"
        mapping[key] = m.group(0)
        return key

    return _QUOTE.sub(repl, text), mapping


def _restore(text: str, mapping: dict[str, str]) -> str:
    for k, v in mapping.items():
        text = text.replace(k, v)
    return text


def parse(text: str, ctx: ParseContext) -> ParseResult:
    res = ParseResult()
    t = (text or "").replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'").strip()
    protected, mapping = _protect_quotes(t)
    if _PREVIEW.search(protected):
        res.dry_run = True
    protected = _PREVIEW.sub(" ", protected)
    clauses = [c for c in _SPLIT.split(protected) if c and c.strip(" ,.")]
    try:
        for raw in clauses:
            clause = _restore(raw, mapping).strip().strip(",").strip()
            clause = _TRAIL.sub("", _FILLER.sub("", clause)).strip()
            clause = re.sub(r"^(?:but|and|also|so)\s+", "", clause, flags=re.I).strip()
            clause = re.sub(r"[.!?]+$", "", clause).strip()
            clause = re.sub(r"\s+", " ", clause)
            if not clause:
                continue
            for parser in _PARSERS:
                out = parser(clause, ctx, res)
                if out is not None:
                    res.items.extend(out)
                    break
            else:
                raise NeedsClarification(UNKNOWN_MSG, "generic")
    except NeedsClarification as q:
        res.items = []
        res.clarification, res.clarification_kind = q.question, q.kind
    if not res.items and not res.clarification and not res.help:
        res.clarification, res.clarification_kind = UNKNOWN_MSG, "generic"
    return res

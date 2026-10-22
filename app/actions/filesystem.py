"""Filesystem primitives.

None of these functions overwrite: writes use exclusive-create mode or an explicit
existence check, and 'delete' is a move into a quarantine folder."""
from __future__ import annotations

import errno
import fnmatch
import hashlib
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from app.core.permissions import TRASH_DIR

IMAGE_EXTS = ["jpg", "jpeg", "png", "gif", "bmp", "webp", "tif", "tiff", "heic", "svg", "ico"]
DOC_EXTS = ["pdf", "doc", "docx", "txt", "md", "rtf", "odt", "xls", "xlsx", "csv", "ppt", "pptx", "ods", "odp"]
ARCHIVE_EXTS = ["zip", "rar", "7z", "tar", "gz", "bz2", "xz"]
AUDIO_EXTS = ["mp3", "wav", "flac", "aac", "ogg", "m4a", "wma"]
VIDEO_EXTS = ["mp4", "mkv", "avi", "mov", "wmv", "webm", "flv"]
CODE_EXTS = ["py", "js", "ts", "html", "htm", "css", "json", "java", "c", "cpp", "h", "cs", "go", "rs", "php", "rb",
             "sh", "ipynb", "xml", "yml", "yaml", "sql", "toml", "ini"]

CATEGORIES: dict[str, list[str]] = {
    "Images": IMAGE_EXTS, "Documents": DOC_EXTS, "Archives": ARCHIVE_EXTS,
    "Audio": AUDIO_EXTS, "Video": VIDEO_EXTS, "Code": CODE_EXTS,
}
EXT_TO_CATEGORY = {e: cat for cat, exts in CATEGORIES.items() for e in exts}
KNOWN_EXTS = set(EXT_TO_CATEGORY)
HASH_LIMIT = 200 * 1024 * 1024  # verify copies by hash up to 200 MB, by size above that


def category_for(name: str) -> str:
    return EXT_TO_CATEGORY.get(Path(name).suffix.lower().lstrip("."), "Other")


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def same_content(a: Path, b: Path) -> bool:
    if a.is_dir() or b.is_dir():
        return a.is_dir() and b.is_dir() and _tree_size(a) == _tree_size(b)
    sa, sb = a.stat().st_size, b.stat().st_size
    if sa != sb:
        return False
    return sa > HASH_LIMIT or sha256_file(a) == sha256_file(b)


def _tree_size(p: Path) -> tuple[int, int]:
    count = total = 0
    for dirpath, dirnames, filenames in os.walk(p):
        dirnames[:] = [d for d in dirnames if d != TRASH_DIR]
        for fn in filenames:
            count += 1
            total += os.path.getsize(os.path.join(dirpath, fn))
    return count, total


def unique_path(path: Path) -> Path:
    """'report.txt' -> 'report (1).txt' (first free name)."""
    stem, suffix = (path.name, "") if path.is_dir() else (path.stem, path.suffix)
    for i in range(1, 1000):
        cand = path.with_name(f"{stem} ({i}){suffix}")
        if not cand.exists():
            return cand
    raise FileExistsError(f"no free name for {path.name}")


def _is_hidden(name: str) -> bool:
    return name == TRASH_DIR or name.startswith(".")


def list_entries(folder: Path, *, extensions=(), pattern: str | None = None, recursive: bool = False,
                 limit: int = 2000, include_dirs: bool = True) -> tuple[list[dict], bool]:
    """List a folder (optionally recursively). Returns (rows, truncated)."""
    exts = {e.lower() for e in extensions or []}
    pat = pattern.lower() if pattern else None
    rows: list[dict] = []

    def visit(dirpath: str, dirnames: list[str], filenames: list[str]) -> bool:
        for name, is_dir in [(d, True) for d in sorted(dirnames, key=str.lower)] + \
                            [(f, False) for f in sorted(filenames, key=str.lower)]:
            if _is_hidden(name):
                continue
            if is_dir and (exts or not include_dirs):
                continue
            ext = "" if is_dir else Path(name).suffix.lower().lstrip(".")
            if exts and ext not in exts:
                continue
            if pat and not fnmatch.fnmatch(name.lower(), pat):
                continue
            full = Path(dirpath) / name
            try:
                st = full.stat()
            except OSError:
                continue
            rows.append({
                "name": name,
                "relative": full.relative_to(folder).as_posix(),
                "kind": "folder" if is_dir else "file",
                "ext": ext,
                "category": "Folder" if is_dir else category_for(name),
                "size": 0 if is_dir else st.st_size,
                "size_h": "—" if is_dir else human_size(st.st_size),
                "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
            if len(rows) >= limit:
                return True
        return False

    if recursive:
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames[:] = [d for d in dirnames if not _is_hidden(d)]
            if visit(dirpath, dirnames, filenames):
                return rows, True
    else:
        dirs, files = [], []
        with os.scandir(folder) as it:
            for e in it:
                (dirs if e.is_dir(follow_symlinks=False) else files).append(e.name)
        if visit(str(folder), dirs, files):
            return rows, True
    return rows, False


def create_folder(path: Path) -> None:
    path.mkdir(parents=False, exist_ok=False)


def copy_path(src: Path, dst: Path) -> None:
    if dst.exists():
        raise FileExistsError(str(dst))
    if src.is_dir():
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(TRASH_DIR))
        return
    with open(src, "rb") as fi, open(dst, "xb") as fo:  # 'x' = never overwrite
        shutil.copyfileobj(fi, fo, 1 << 20)
    shutil.copystat(src, dst)


def move_path(src: Path, dst: Path) -> None:
    case_only = os.path.normcase(str(src)) == os.path.normcase(str(dst)) and str(src) != str(dst)
    if dst.exists() and not case_only:
        raise FileExistsError(str(dst))
    try:
        os.rename(src, dst)  # on Windows os.rename never replaces an existing file
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        copy_path(src, dst)  # cross-volume: copy, verify, then remove the original
        if not same_content(src, dst):
            raise OSError("cross-volume move verification failed; original kept") from exc
        shutil.rmtree(src) if src.is_dir() else src.unlink()


def quarantine(path: Path, trash_dir: Path) -> Path:
    trash_dir.mkdir(exist_ok=True)
    dest = trash_dir / f"{datetime.now():%Y%m%d-%H%M%S}_{path.name}"
    if dest.exists():
        dest = unique_path(dest)
    move_path(path, dest)
    return dest


def write_new_text(path: Path, content: str) -> None:
    with open(path, "x", encoding="utf-8", newline="") as f:
        f.write(content)


def make_zip(folder: Path, zip_path: Path) -> int:
    count = 0
    with zipfile.ZipFile(zip_path, "x", zipfile.ZIP_DEFLATED) as z:
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames[:] = [d for d in dirnames if d != TRASH_DIR]
            for fn in sorted(filenames):
                full = Path(dirpath) / fn
                if os.path.normcase(str(full)) == os.path.normcase(str(zip_path)):
                    continue
                z.write(full, full.relative_to(folder).as_posix())
                count += 1
    return count


def verify_zip(zip_path: Path, expected: int) -> bool:
    with zipfile.ZipFile(zip_path) as z:
        return z.testzip() is None and len(z.namelist()) == expected


def find_duplicates(folder: Path, recursive: bool = True, limit: int = 5000) -> list[list[Path]]:
    by_size: dict[int, list[Path]] = {}
    seen = 0
    walker = os.walk(folder) if recursive else [(str(folder), [], [e.name for e in os.scandir(folder) if e.is_file()])]
    for dirpath, dirnames, filenames in walker:
        dirnames[:] = [d for d in dirnames if not _is_hidden(d)]
        for fn in filenames:
            if _is_hidden(fn):
                continue
            p = Path(dirpath) / fn
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if size:
                by_size.setdefault(size, []).append(p)
            seen += 1
            if seen >= limit:
                break
    groups: list[list[Path]] = []
    for paths in by_size.values():
        if len(paths) < 2:
            continue
        by_hash: dict[str, list[Path]] = {}
        for p in paths:
            by_hash.setdefault(sha256_file(p), []).append(p)
        groups.extend(sorted(g) for g in by_hash.values() if len(g) > 1)
    return groups

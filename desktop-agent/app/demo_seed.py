"""Creates the harmless demo workspace (fake sample files only) and can reset it."""
from __future__ import annotations

import io
import json
import shutil
import zipfile
from pathlib import Path

TEXT_FILES = {
    "welcome.txt": "Welcome to the AI Desktop Automation Agent demo workspace.\n"
                   "Everything in this folder is fake sample data — safe to rename, move and organize.\n",
    "quick_todo.txt": "- Try: Organize my files by type, but show me the proposed changes first\n- Try: Zip the Projects folder\n",
    "Downloads/meeting_notes.txt": "Meeting notes (sample)\n- Review roadmap\n- Assign owners\n- Next sync Friday\n",
    "Downloads/notes_copy.txt": "Meeting notes (sample)\n- Review roadmap\n- Assign owners\n- Next sync Friday\n",
    "Downloads/budget_q3.csv": "item,amount\nlaptops,4200\nsoftware,0\ntraining,650\n",
    "Downloads/setup_notes.md": "# Setup notes\nInstall Python 3.11+, run setup.bat, then run.bat.\n",
    "Downloads/data_export.json": json.dumps({"sample": True, "records": [1, 2, 3]}, indent=2) + "\n",
    "Downloads/script_example.py": "# Harmless sample file. The agent never executes scripts.\nprint('hello')\n",
    "Downloads/page_draft.html": "<!doctype html><title>Draft</title><h1>Sample page</h1>\n",
    "Documents/report_draft.txt": "Quarterly report — DRAFT (sample data)\nRevenue grew in the sample scenario.\n",
    "Documents/meeting_notes.txt": "Meeting notes (sample)\n- Review roadmap\n- Assign owners\n- Next sync Friday\n",
    "Documents/inventory.csv": "sku,name,qty\nA-100,Widget,12\nB-200,Gadget,4\n",
    "Projects/README.md": "# Projects\nSample project folder for the automation demo.\n",
    "Projects/roadmap.txt": "Q1: prototype\nQ2: beta\nQ3: launch\n",
    "Projects/Website/index.html": "<!doctype html><title>Demo site</title><p>Hello</p>\n",
    "Projects/Website/style.css": "body { font-family: sans-serif; }\n",
    "README_DEMO.txt": "This folder is the agent's default approved folder (alias 'Demo').\n"
                       "Use Settings → Workspace → Reset demo workspace to restore it at any time.\n",
}
IMAGES = {
    "logo.png": ((34, 211, 238), (37, 99, 235)),
    "Downloads/holiday_photo.png": ((251, 191, 36), (239, 68, 68)),
    "Downloads/screenshot_ui.png": ((15, 23, 42), (56, 189, 248)),
    "Photos/IMG_1001.jpg": ((14, 165, 233), (16, 185, 129)),
    "Photos/IMG_1002.jpg": ((168, 85, 247), (59, 130, 246)),
    "Photos/IMG_1003.jpg": ((244, 114, 182), (251, 146, 60)),
    "Photos/beach.png": ((56, 189, 248), (253, 224, 71)),
}


def _image(path: Path, c1, c2) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:  # Pillow ships with Streamlit; fall back to a tiny text placeholder
        path.with_suffix(".txt").write_text("image placeholder\n", encoding="utf-8")
        return
    w, h = 320, 200
    img = Image.new("RGB", (w, h), c1)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        draw.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)))
    draw.ellipse([w * 0.62, h * 0.18, w * 0.86, h * 0.56], fill=(255, 255, 255))
    draw.polygon([(0, h), (w * 0.35, h * 0.45), (w * 0.7, h)], fill=(2, 8, 23))
    img.save(path, quality=85)


def _pdf(path: Path, title: str) -> None:
    try:
        from reportlab.lib.pagesizes import A5
        from reportlab.pdfgen import canvas
    except ImportError:
        path.with_suffix(".txt").write_text(title + "\n", encoding="utf-8")
        return
    c = canvas.Canvas(str(path), pagesize=A5)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, 520, title)
    c.setFont("Helvetica", 10)
    c.drawString(40, 495, "Sample document generated for the demo workspace.")
    c.drawString(40, 480, "Total: 0.00 (fake data)")
    c.save()


def seed_demo_workspace(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, text in TEXT_FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text(text, encoding="utf-8")
    for rel, (c1, c2) in IMAGES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            _image(p, c1, c2)
    for rel, title in {"Downloads/invoice_2026_03.pdf": "Invoice #2026-03 (sample)",
                       "Documents/policy_summary.pdf": "Policy summary (sample)"}.items():
        p = root / rel
        if not p.exists():
            _pdf(p, title)
    z = root / "Downloads" / "project_backup.zip"
    if not z.exists():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("backup/readme.txt", "sample backup\n")
        z.write_bytes(buf.getvalue())
    (root / "Archive").mkdir(exist_ok=True)
    return root


def reset_demo_workspace(root: Path, expected: Path) -> None:
    """Wipe and re-create ONLY the configured demo folder."""
    if root.resolve() != expected.resolve():
        raise ValueError("Refusing to reset a folder that is not the demo workspace.")
    if root.exists():
        for child in root.iterdir():
            shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)  # tolerate sync-client locks
    seed_demo_workspace(root)


def copy_demo_to(dest: Path, source: Path) -> Path:
    if not source.exists() or not any(source.iterdir()):
        seed_demo_workspace(source)
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns(".agent_trash"), dirs_exist_ok=True)
    return dest

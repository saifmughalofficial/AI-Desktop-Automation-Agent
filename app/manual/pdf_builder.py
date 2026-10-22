"""Builds docs/User_Manual.pdf from app.manual.content (ReportLab, dark-cover theme)."""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from app.manual.content import SECTIONS, SUBTITLE, TITLE, VERSION
from app.runtime import DOCS_DIR

NAVY = colors.HexColor("#020817")
PANEL = colors.HexColor("#0b2447")
CYAN = colors.HexColor("#22d3ee")
SKY = colors.HexColor("#0ea5e9")
INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#475569")
_SAFE = {"→": "->", "✓": "OK", "✕": "x", "•": "-", "…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-",
         "—": " - ", "·": "|", "≥": ">=", "⚠": "!"}


def _t(text: str) -> str:
    for k, v in _SAFE.items():
        text = text.replace(k, v)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=17, textColor=SKY,
                             spaceBefore=4, spaceAfter=8),
        "body": ParagraphStyle("body", parent=ss["BodyText"], fontName="Helvetica", fontSize=10, leading=14.5,
                               textColor=INK, spaceAfter=6),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.8, leading=11.5, textColor=INK),
        "cellh": ParagraphStyle("cellh", fontName="Helvetica-Bold", fontSize=9, leading=11.5, textColor=colors.white),
        "cap": ParagraphStyle("cap", fontName="Helvetica-Oblique", fontSize=8.5, textColor=MUTED, alignment=TA_CENTER,
                              spaceBefore=3, spaceAfter=10),
        "toc": ParagraphStyle("toc", fontName="Helvetica", fontSize=11, leading=19, textColor=INK),
    }


def _cover(c, doc):
    w, h = A4
    c.saveState()
    c.setFillColor(NAVY)
    c.rect(0, 0, w, h, fill=1, stroke=0)
    c.setStrokeColor(colors.HexColor("#0c2a4d"))
    c.setLineWidth(0.4)
    for x in range(0, int(w), 28):
        c.line(x, 0, x, h)
    for y in range(0, int(h), 28):
        c.line(0, y, w, y)
    cx, cy = w / 2, h * 0.60
    for i, r in enumerate((150, 118, 88)):
        c.setStrokeColor(CYAN if i == 0 else SKY)
        c.setLineWidth(2.2 - i * 0.5)
        c.setDash(6 if i == 1 else 1, 0 if i != 1 else 8)
        c.circle(cx, cy, r, fill=0, stroke=1)
    c.setDash()
    import random
    rnd = random.Random(7)
    pts = []
    for _ in range(90):
        while True:
            x, y = rnd.uniform(-1, 1), rnd.uniform(-0.8, 0.8)
            side = -0.5 if x < 0 else 0.5
            if ((x - side) / 0.55) ** 2 + (y / 0.8) ** 2 < 1 and abs(x) > 0.05:
                pts.append((cx + x * 70, cy + y * 70))
                break
    c.setStrokeColor(colors.Color(0.13, 0.83, 0.93, alpha=0.45))
    c.setLineWidth(0.5)
    for i, (x1, y1) in enumerate(pts):
        for x2, y2 in pts[i + 1:]:
            if (x1 - x2) ** 2 + (y1 - y2) ** 2 < 420:
                c.line(x1, y1, x2, y2)
    c.setFillColor(colors.HexColor("#a5f3fc"))
    for x, y in pts:
        c.circle(x, y, 1.4, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(cx, h * 0.33, TITLE.upper())
    c.setFillColor(CYAN)
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(cx, h * 0.33 - 30, SUBTITLE)
    c.setFillColor(colors.HexColor("#7ea6cc"))
    c.setFont("Helvetica", 11)
    c.drawCentredString(cx, h * 0.33 - 56, "Local-first  |  Policy-guarded  |  Offline-capable  |  No paid APIs")
    c.drawCentredString(cx, 60, f"Version {VERSION}  |  {date.today():%B %Y}")
    c.setStrokeColor(CYAN)
    c.setLineWidth(2)
    c.line(w * 0.25, h * 0.33 - 72, w * 0.75, h * 0.33 - 72)
    c.restoreState()


def _page(c, doc):
    w, h = A4
    c.saveState()
    c.setFillColor(NAVY)
    c.rect(0, h - 22 * mm, w, 22 * mm, fill=1, stroke=0)
    c.setFillColor(CYAN)
    c.rect(0, h - 22 * mm, w, 1.2, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.white)
    c.drawString(18 * mm, h - 13 * mm, TITLE.upper())
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#7ea6cc"))
    c.drawRightString(w - 18 * mm, h - 13 * mm, SUBTITLE)
    c.setFillColor(MUTED)
    c.drawCentredString(w / 2, 12 * mm, f"Page {doc.page}")
    c.restoreState()


def _table(rows, st, widths=None):
    data = [[Paragraph(_t(str(x)), st["cellh"] if i == 0 else st["cell"]) for x in row] for i, row in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PANEL),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef7fc")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b6d4e6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    return t


def build_pdf(out: Path | None = None, screenshots: Path | None = None) -> bytes:
    st = _styles()
    shots = screenshots or DOCS_DIR / "screenshots"
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=30 * mm,
                            bottomMargin=20 * mm, title=f"{TITLE} - {SUBTITLE}", author="AI Desktop Automation Agent",
                            subject="User manual")
    width = A4[0] - 36 * mm
    story: list = [PageBreak(), Paragraph("Contents", st["h1"])]
    for title, _ in SECTIONS:
        story.append(Paragraph(_t(title), st["toc"]))
    story.append(PageBreak())
    for title, blocks in SECTIONS:
        story.append(Paragraph(_t(title), st["h1"]))
        for b in blocks:
            if b[0] == "p":
                story.append(Paragraph(_t(b[1]), st["body"]))
            elif b[0] == "ul":
                story.append(ListFlowable([ListItem(Paragraph(_t(x), st["body"]), leftIndent=12) for x in b[1]],
                                          bulletType="bullet", start="-", leftIndent=12, bulletColor=SKY))
            elif b[0] == "table":
                cols = len(b[1][0])
                widths = [width * 0.26, width * 0.74] if cols == 2 else [width * 0.14, width * 0.43, width * 0.43]
                story += [_table(b[1], st, widths), Spacer(1, 8)]
            elif b[0] == "img":
                p = shots / b[1]
                if p.exists():
                    from reportlab.lib.utils import ImageReader
                    iw, ih = ImageReader(str(p)).getSize()
                    w = width
                    h = w * ih / iw
                    if h > 120 * mm:
                        h, w = 120 * mm, 120 * mm * iw / ih
                    story.append(KeepTogether([Image(str(p), width=w, height=h), Paragraph(_t(b[2]), st["cap"])]))
        story.append(Spacer(1, 10))
    doc.build(story, onFirstPage=_cover, onLaterPages=_page)
    data = buf.getvalue()
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    return data


def build_markdown() -> str:
    out = [f"# {TITLE} — {SUBTITLE}", "", f"Version {VERSION}. The PDF version is `docs/User_Manual.pdf`.", ""]
    for title, blocks in SECTIONS:
        out += [f"## {title}", ""]
        for b in blocks:
            if b[0] == "p":
                out += [b[1], ""]
            elif b[0] == "ul":
                out += [f"- {x}" for x in b[1]] + [""]
            elif b[0] == "table":
                out.append("| " + " | ".join(b[1][0]) + " |")
                out.append("|" + "---|" * len(b[1][0]))
                out += ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in b[1][1:]]
                out.append("")
            elif b[0] == "img":
                out += [f"![{b[2]}](screenshots/{b[1]})", ""]
    return "\n".join(out)


if __name__ == "__main__":
    target = DOCS_DIR / "User_Manual.pdf"
    build_pdf(target)
    (DOCS_DIR / "USER_GUIDE.md").write_text(build_markdown(), encoding="utf-8")
    print(f"Wrote {target} and USER_GUIDE.md")

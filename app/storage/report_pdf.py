"""One-task PDF report (request, approval, every action with its verified outcome)."""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.manual.pdf_builder import _t

NAVY = colors.HexColor("#0b1d3a")


def task_report_pdf(task: dict, actions: list[dict]) -> bytes:
    h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=16, textColor=colors.HexColor("#2563eb"), spaceAfter=6)
    b = ParagraphStyle("b", fontName="Helvetica", fontSize=9.5, leading=13)
    c = ParagraphStyle("c", fontName="Helvetica", fontSize=8.3, leading=10.5)
    ch = ParagraphStyle("ch", fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.white)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"Task #{task['id']} report")
    meta = [["Task", f"#{task['id']}"], ["Created", task["created_at"]], ["Finished", task.get("finished_at") or "-"],
            ["Status", task["status"].upper()], ["Risk", task["risk"]], ["Approval", task["approval"]],
            ["Engine", task["engine"]], ["Summary", task.get("summary") or "-"]]
    mt = Table([[Paragraph(_t(k), ch), Paragraph(_t(str(v)), b)] for k, v in meta], colWidths=[32 * mm, 146 * mm])
    mt.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), NAVY), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b6d4e6")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    rows = [[Paragraph(x, ch) for x in ("#", "Action", "Target", "Status", "Verified", "Message")]]
    for a in actions:
        rows.append([Paragraph(str(a["step_index"] + 1), c), Paragraph(_t(a["action_type"]), c), Paragraph(_t(a["target"] or ""), c),
                     Paragraph(_t(a["status"]), c), Paragraph("yes" if a["verified"] else "no", c), Paragraph(_t(a["message"] or ""), c)])
    at = Table(rows, colWidths=[8 * mm, 26 * mm, 44 * mm, 18 * mm, 14 * mm, 68 * mm], repeatRows=1)
    at.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b6d4e6")),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef4ff")]),
                            ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story = [Paragraph("AI Desktop Automation Agent - task report", h), Paragraph(_t(task["request"]), b), Spacer(1, 8), mt,
             Spacer(1, 10), Paragraph("Actions", h), at if actions else Paragraph("No actions were executed.", b)]
    doc.build(story)
    return buf.getvalue()

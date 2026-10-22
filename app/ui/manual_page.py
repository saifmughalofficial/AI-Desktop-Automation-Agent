"""Manual page: download the PDF instruction manual and read it in the app."""
from __future__ import annotations

import streamlit as st

from app.manual.content import SECTIONS
from app.manual.pdf_builder import build_pdf
from app.runtime import DOCS_DIR
from app.ui import components as C
from app.ui.theme import esc


@st.cache_data(show_spinner="Building PDF manual…")
def _pdf_bytes() -> bytes:
    path = DOCS_DIR / "User_Manual.pdf"
    return path.read_bytes() if path.exists() else build_pdf()


def _block_html(b) -> str:
    if b[0] == "p":
        return f"<p>{esc(b[1])}</p>"
    if b[0] == "ul":
        return "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in b[1]) + "</ul>"
    if b[0] == "table":
        head = "".join(f"<th>{esc(x)}</th>" for x in b[1][0])
        rows = "".join("<tr>" + "".join(f"<td>{esc(x)}</td>" for x in r) + "</tr>" for r in b[1][1:])
        return f"<table><tr>{head}</tr>{rows}</table>"
    return ""


def render() -> None:
    st.markdown(C.page_title("Manual", "Instructions · commands · safety model · deployment", "book"),
                unsafe_allow_html=True)
    c1, c2 = st.columns([1.3, 3], vertical_alignment="center")
    c1.download_button("Download PDF manual", _pdf_bytes(), "AI_Desktop_Automation_Agent_Manual.pdf",
                       "application/pdf", type="primary", icon=":material/picture_as_pdf:", width="stretch")
    c2.caption("The same manual is included in the project as docs/User_Manual.pdf, with screenshots.")
    shots = DOCS_DIR / "screenshots"
    for title, blocks in SECTIONS:
        with st.expander(title, expanded=title.startswith(("1.", "6.", "7."))):
            body, imgs = [], []
            for b in blocks:
                if b[0] == "img":
                    imgs.append(b)
                else:
                    body.append(_block_html(b))
            st.html(f"<div class='manual'>{''.join(body)}</div>")
            for b in imgs:
                if (shots / b[1]).exists():
                    st.image(str(shots / b[1]), caption=b[2])

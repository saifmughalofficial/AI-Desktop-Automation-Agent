"""HUD widgets rendered as HTML/SVG strings (st.markdown, so updates are diffed in place)."""
from __future__ import annotations

import math

from app.ui.theme import esc

ICONS = {
    "cpu": '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>',
    "flow": '<circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="12" cy="18" r="2"/><path d="M7 6h10M6 8l5 8M18 8l-5 8"/>',
    "brain": '<path d="M9 3a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 3 3 3 3 0 0 0 3-3V6a3 3 0 0 0-3-3z"/><path d="M15 3a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-3 3 3 3 0 0 1-3-3"/>',
    "terminal": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M6 9l3 3-3 3M12 15h6"/>',
    "chart": '<path d="M3 3v18h18"/><path d="M7 15l4-5 3 3 5-7"/>',
    "disk": '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "tasks": '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2"/>',
    "plan": '<path d="M9 4h6l1 2h3v15H5V6h3z"/><path d="M9 12h6M9 16h4"/>',
    "shield": '<path d="M12 2l8 4v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6z"/><path d="M9 12l2 2 4-4"/>',
    "play": '<circle cx="12" cy="12" r="10"/><path d="M10 8l6 4-6 4z"/>',
    "folder": '<path d="M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "app": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 8h18M7 6h.01M10 6h.01"/>',
    "history": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 3"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "book": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M8 7h8M8 11h6"/>',
    "rules": '<path d="M4 6h16M4 12h10M4 18h7"/><circle cx="18" cy="16" r="3"/>',
    "model": '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 9h6v6H9z"/>',
    "exec": '<path d="M13 2L3 14h8l-1 8 10-12h-8z"/>',
    "eye": '<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>',
    "log": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h5"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
}


def icon(name: str, cls: str = "") -> str:
    return f'<svg class="{cls}" viewBox="0 0 24 24">{ICONS.get(name, ICONS["app"])}</svg>'


def _clean(s: str) -> str:
    # st.markdown treats indented lines as code and blank lines as paragraph breaks: emit one tight line.
    return "".join(line.strip() for line in s.splitlines())


def panel(title: str, ico: str, body: str, meta: str = "") -> str:
    tail = f'<span class="meta">{esc(meta)}</span>' if meta else '<span class="tail"><i></i><i></i><i></i></span>'
    return _clean(f"""<div class="hud"><i class="cn c1"></i><i class="cn c2"></i><i class="cn c3"></i><i class="cn c4"></i>
<div class="hud-t">{icon(ico)}<span>{esc(title)}</span>{tail}</div>{body}</div>""")


def page_title(title: str, sub: str, ico: str) -> str:
    return _clean(f"""<div class="page-title"><div class="ico">{icon(ico)}</div><div><h1>{esc(title)}</h1>
<div class="sub">{esc(sub)}</div></div></div>""")


def level_color(v: float) -> str:
    return "#22d3ee" if v < 60 else ("#fbbf24" if v < 85 else "#f87171")


def gauge(label: str, value: float | None, sub: str = "") -> str:
    v = 0.0 if value is None else max(0.0, min(100.0, float(value)))
    r = 34
    c = 2 * math.pi * r
    off = c * (1 - v / 100)
    col = level_color(v)
    num = "—" if value is None else f"{v:.0f}%"
    return _clean(f"""<div class="gauge"><svg viewBox="0 0 100 100">
<circle class="g-ring" cx="50" cy="50" r="46" stroke="{col}"/>
<circle class="g-ticks" cx="50" cy="50" r="41"/>
<circle class="g-track" cx="50" cy="50" r="{r}"/>
<circle class="g-val" cx="50" cy="50" r="{r}" stroke="{col}" stroke-dasharray="{c:.1f}" stroke-dashoffset="{off:.1f}"
 transform="rotate(-90 50 50)" style="filter:drop-shadow(0 0 5px {col})"/>
<text class="g-lbl" x="50" y="44" text-anchor="middle">{esc(label)}</text>
<text class="g-num" x="50" y="62" text-anchor="middle">{num}</text></svg>
<div class="g-sub">{esc(sub)}</div></div>""")


def area_chart(label: str, values: list[float], value_text: str, color: str, vmax: float | None = None) -> str:
    vals = list(values)[-40:] or [0.0]
    if len(vals) == 1:
        vals = vals * 2
    top = vmax or max(max(vals) * 1.25, 1.0)
    w, h = 300, 46
    n = len(vals)
    pts = [(i * w / (n - 1), h - 3 - (min(v, top) / top) * (h - 8)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"0,{h} {line} {w},{h}"
    gid = "g" + "".join(ch for ch in label if ch.isalnum())
    lx, ly = pts[-1]
    return _clean(f"""<div class="chart"><div class="chart-h"><span>{esc(label)}</span><b>{esc(value_text)}</b></div>
<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none"><defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="{color}" stop-opacity=".45"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>
<polygon points="{area}" fill="url(#{gid})"/><polyline class="ln" points="{line}" stroke="{color}" style="color:{color}"/>
<circle class="dot" cx="{lx:.1f}" cy="{ly:.1f}" r="3" fill="{color}"/></svg></div>""")


FLOW_NODES = [("INPUT", 10, 12), ("PLANNER", 112, 12), ("POLICY", 214, 12),
              ("AUDIT", 10, 92), ("VERIFY", 112, 92), ("EXECUTOR", 214, 92)]


def dataflow(active: str | None) -> str:
    nodes = "".join(
        f'<g class="node{" on" if active == n else ""}"><rect x="{x}" y="{y}" width="76" height="30"/>'
        f'<text x="{x + 38}" y="{y + 19}" text-anchor="middle">{n}</text></g>' for n, x, y in FLOW_NODES)
    wires = ["M86 27H112", "M188 27H214", "M252 42V92", "M214 107H188", "M112 107H86", "M48 92V42"]
    paths = "".join(f'<path class="wire" d="{d}"/><path class="pulse" d="{d}"/>' for d in wires)
    defs = ('<defs><linearGradient id="flowgrad" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="300" y2="134">'
            '<stop offset="0" stop-color="#38bdf8"/><stop offset=".5" stop-color="#a855f7"/>'
            '<stop offset="1" stop-color="#ff2d55"/></linearGradient></defs>')
    return _clean(f'<div class="flow"><svg viewBox="0 0 300 134">{defs}{paths}{nodes}</svg></div>')


def status_line(text: str, tone: str = "") -> str:
    return f'<div class="status-line"><span class="dot {tone}"></span>{esc(text)}</div>'


def agent_row(name: str, desc: str, state: str, tone: str, ico: str, pct: float, running: bool = False) -> str:
    color = {"": "#34d399", "amber": "#fbbf24", "red": "#f87171", "off": "#94a3b8"}[tone]
    return _clean(f"""<div class="agent">{icon(ico)}<div><div class="nm">{esc(name)}</div><div class="ds">{esc(desc)}</div>
<div class="bar{' run' if running else ''}"><i style="width:{max(0, min(100, pct)):.0f}%"></i></div></div>
<div class="st" style="color:{color}"><span class="dot {tone}"></span>{esc(state)}</div></div>""")


def terminal(lines: list[tuple[str, str, str]], limit: int = 11) -> str:
    rows = []
    for ts, lvl, msg in lines[-limit:]:
        rows.append(f'<div class="l"><span class="t">{esc(ts)}</span> <span class="p">&gt;</span> '
                    f'<span class="{esc(lvl)}">{esc(msg)}</span></div>')
    rows.append('<div class="l"><span class="p">&gt;</span> <span class="cur"></span></div>')
    return f'<div class="term">{"".join(rows)}</div>'


def donut(pct: float, label_html: str) -> str:
    r = 38
    c = 2 * math.pi * r
    off = c * (1 - max(0, min(100, pct)) / 100)
    col = level_color(pct)
    return _clean(f"""<div class="store"><svg viewBox="0 0 100 100">
<circle cx="50" cy="50" r="46" fill="none" stroke="rgba(56,189,248,.18)" stroke-dasharray="2 4"/>
<circle cx="50" cy="50" r="{r}" fill="none" stroke="rgba(56,189,248,.12)" stroke-width="9"/>
<circle cx="50" cy="50" r="{r}" fill="none" stroke="{col}" stroke-width="9" stroke-linecap="round" stroke-dasharray="{c:.1f}"
 stroke-dashoffset="{off:.1f}" transform="rotate(-90 50 50)" style="transition:stroke-dashoffset 1s;filter:drop-shadow(0 0 5px {col})"/>
<text x="50" y="56" text-anchor="middle" style="font-family:Orbitron;font-size:17px;font-weight:800;fill:#fff">{pct:.0f}%</text>
</svg><div class="kv">{label_html}</div></div>""")


def task_bar(name: str, pct: float, right: str, running: bool = False) -> str:
    return _clean(f"""<div class="task"><div class="hd"><span>{esc(name)}</span><span>{esc(right)}</span></div>
<div class="bar{' run' if running else ''}"><i style="width:{max(2, min(100, pct)):.0f}%"></i></div></div>""")


def risk_badge(risk: str) -> str:
    return f'<span class="risk {esc(risk)}">● {esc(risk)}</span>'


def chip(text: str) -> str:
    return f'<span class="chip">{esc(text)}</span>'


def callout(kind: str, html_body: str) -> str:
    return f'<div class="callout {kind}">{html_body}</div>'


STATUS_ICON = {"pending": "", "running": "", "success": "✓", "unverified": "?", "simulated": "◇", "skipped": "↷",
               "failed": "✕", "cancelled": "–", "paused": "Ⅱ"}


def step_row(i: int, desc: str, status: str, msg: str) -> str:
    return _clean(f"""<div class="srow {esc(status)}"><div class="ic {esc(status)}">{STATUS_ICON.get(status, '') or i}</div>
<div><div class="d">{esc(desc)}</div>{f'<div class="m">{esc(msg)}</div>' if msg else ''}</div>
<div class="s">{esc(status)}</div></div>""")


def progress(pct: float, done: bool) -> str:
    return f'<div class="prog{" done" if done else ""}"><i style="width:{max(2, pct * 100):.0f}%"></i></div>'


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in {"B", "KB"} else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"

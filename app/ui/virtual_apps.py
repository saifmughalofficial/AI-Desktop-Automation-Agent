"""Renders the web virtual desktop windows (hosted mode): working Notepad, Calculator, Paint,
Character Map, file viewer and folder viewer."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.ui import components as C
from app.ui import state
from app.ui.theme import esc

_BASE = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700&family=Rajdhani:wght@600;700&display=swap" rel="stylesheet">
<style>html,body{margin:0;background:transparent;color:#e6f6ff;font-family:Rajdhani,system-ui,sans-serif}
button{font-family:Rajdhani;font-weight:700;cursor:pointer;border-radius:9px;border:1px solid rgba(168,85,247,.45);
background:linear-gradient(180deg,rgba(20,40,90,.9),rgba(8,14,40,.95));color:#e6f6ff;transition:all .15s}
button:hover{border-color:#fb7185;box-shadow:0 0 14px rgba(255,45,85,.35),0 0 10px rgba(56,189,248,.3);transform:translateY(-1px)}
button:active{transform:scale(.96)}</style></head><body>"""

CALC = _BASE + """<style>.c{max-width:330px;margin:0 auto;padding:6px}
.d{font-family:Orbitron;font-size:30px;text-align:right;padding:14px 12px;border-radius:10px;margin-bottom:8px;min-height:40px;
background:rgba(2,6,20,.9);border:1px solid rgba(56,189,248,.4);box-shadow:inset 0 0 18px rgba(56,189,248,.15);overflow:hidden;
text-shadow:0 0 12px rgba(56,189,248,.8)}.h{font-size:12px;color:#7ea6cc;text-align:right;min-height:16px}
.g{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}.g button{height:46px;font-size:19px}
.op{color:#fda4af}.eq{background:linear-gradient(90deg,#2563eb,#7c3aed,#e11d48)!important;border-color:#f9a8d4!important}</style>
<div class="c"><div class="h" id="h"></div><div class="d" id="d">0</div><div class="g" id="g"></div></div>
<script>
const keys=['C','(',')','/','7','8','9','*','4','5','6','-','1','2','3','+','0','.','DEL','='];
let e='';const d=document.getElementById('d'),h=document.getElementById('h'),g=document.getElementById('g');
function show(){d.textContent=e||'0';}
function calc(){if(!/^[0-9+\\-*/(). ]+$/.test(e)){d.textContent='Error';e='';return;}
 try{const r=Function('"use strict";return ('+e+')')();h.textContent=e+' =';e=String(Math.round(r*1e10)/1e10);show();}catch(x){d.textContent='Error';e='';}}
function press(k){if(k==='C'){e='';h.textContent='';}else if(k==='DEL'){e=e.slice(0,-1);}else if(k==='='){calc();return;}else{e+=k;}show();}
keys.forEach(k=>{const b=document.createElement('button');b.textContent=k;if('/*-+'.includes(k))b.className='op';if(k==='=')b.className='eq';
 b.onclick=()=>press(k);g.appendChild(b);});
document.addEventListener('keydown',ev=>{if('0123456789+-*/().'.includes(ev.key))press(ev.key);else if(ev.key==='Enter')press('=');else if(ev.key==='Backspace')press('DEL');else if(ev.key==='Escape')press('C');});
</script></body></html>"""

PAINT = _BASE + """<style>.t{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:6px}.t button{padding:5px 10px;font-size:13px}
.sw{width:22px;height:22px;border-radius:50%;border:2px solid rgba(255,255,255,.25);cursor:pointer}.sw.on{border-color:#fff;box-shadow:0 0 10px #fff}
canvas{width:100%;height:270px;border-radius:10px;border:1px solid rgba(168,85,247,.45);background:#050a1c;touch-action:none;cursor:crosshair}
input[type=range]{accent-color:#a855f7}</style>
<div class="t" id="t"></div><canvas id="c"></canvas>
<script>
const c=document.getElementById('c'),x=c.getContext('2d'),t=document.getElementById('t');
function rs(){const im=c.width?x.getImageData(0,0,c.width,c.height):null;c.width=c.clientWidth;c.height=c.clientHeight;x.fillStyle='#050a1c';x.fillRect(0,0,c.width,c.height);if(im)x.putImageData(im,0,0);}
rs();let col='#38bdf8',size=4,down=false,lx=0,ly=0;
['#38bdf8','#a855f7','#ff2d55','#34d399','#fbbf24','#ffffff'].forEach((k,i)=>{const s=document.createElement('div');s.className='sw'+(i?'':' on');s.style.background=k;
 s.onclick=()=>{col=k;document.querySelectorAll('.sw').forEach(n=>n.classList.remove('on'));s.classList.add('on');};t.appendChild(s);});
const r=document.createElement('input');r.type='range';r.min=1;r.max=24;r.value=4;r.oninput=()=>size=+r.value;t.appendChild(r);
const er=document.createElement('button');er.textContent='Eraser';er.onclick=()=>{col='#050a1c';};t.appendChild(er);
const cl=document.createElement('button');cl.textContent='Clear';cl.onclick=()=>{x.fillStyle='#050a1c';x.fillRect(0,0,c.width,c.height);};t.appendChild(cl);
const sv=document.createElement('button');sv.textContent='Save PNG';sv.onclick=()=>{const a=document.createElement('a');a.download='painting.png';a.href=c.toDataURL();a.click();};t.appendChild(sv);
function p(e){const b=c.getBoundingClientRect();return[e.clientX-b.left,e.clientY-b.top];}
c.onpointerdown=e=>{down=true;[lx,ly]=p(e);};window.onpointerup=()=>down=false;
c.onpointermove=e=>{if(!down)return;const[nx,ny]=p(e);x.strokeStyle=col;x.lineWidth=size;x.lineCap='round';x.shadowColor=col;x.shadowBlur=col==='#050a1c'?0:8;
 x.beginPath();x.moveTo(lx,ly);x.lineTo(nx,ny);x.stroke();lx=nx;ly=ny;};
</script></body></html>"""

CHARMAP = _BASE + """<style>.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(38px,1fr));gap:5px;max-height:250px;overflow:auto;padding:2px}
.g button{height:38px;font-size:18px}.s{font-size:13px;color:#7ea6cc;margin:4px 0 8px}.s b{color:#fda4af}</style>
<div class="s">Click a character to copy it. Copied: <b id="o">—</b></div><div class="g" id="g"></div>
<script>
const s='©®™°±×÷€£¥¢§¶•…–—«»¿¡½¼¾αβγδλμπσΩ∞≈≠≤≥√∑∏∫→←↑↓↔★☆♥♦♣♠✓✗☀☁☂☃♪♫⌘⌥⚡⚙☢☯';
const g=document.getElementById('g'),o=document.getElementById('o');
[...s].forEach(ch=>{const b=document.createElement('button');b.textContent=ch;b.onclick=()=>{o.textContent=ch;try{navigator.clipboard.writeText(ch);}catch(e){}};g.appendChild(b);});
</script></body></html>"""


def _sync_text(wid: str, key: str) -> None:
    vd = state.svc().orchestrator.virtual
    win = vd.get(wid) if vd else None
    if win is not None:
        win["text"] = st.session_state.get(key, "")


def render_virtual_desktop() -> None:
    s = state.svc()
    vd = s.orchestrator.virtual
    if vd is None or not vd.windows:
        return
    st.markdown(C.panel("Web virtual desktop", "app",
                        "<div style='font-size:.88rem;color:#bfe3f7'>Cloud sandbox: apps the agent launches open here as "
                        "working web windows. Run the agent locally on Windows (run.bat) to control the real apps.</div>",
                        meta=f"{len(vd.windows)} window(s)"), unsafe_allow_html=True)
    wins = list(vd.windows.values())
    for i in range(0, len(wins), 2):
        cols = st.columns(2)
        for col, win in zip(cols, wins[i:i + 2]):
            with col, st.container(border=True):
                h1, h2 = st.columns([5, 1], vertical_alignment="center")
                h1.markdown(f"<div class='vd-title'><span class='vd-dots'><i></i><i></i><i></i></span>{esc(win['title'])}</div>",
                            unsafe_allow_html=True)
                if h2.button("", icon=":material/close:", key=f"vd_close_{win['id']}", help="Close window"):
                    vd.close(win["id"])
                    st.rerun()
                kind = win["kind"]
                if kind in {"notepad", "wordpad"}:
                    key = f"vd_{win['id']}_{win['rev']}"
                    st.text_area("Document", value=win["text"], key=key, height=220, label_visibility="collapsed",
                                 on_change=_sync_text, args=(win["id"], key), placeholder="Type here…")
                    st.download_button("Save as .txt", win["text"], f"{win['title'].split(' - ')[0]}.txt", "text/plain",
                                       icon=":material/save:", key=f"vd_save_{win['id']}_{win['rev']}")
                elif kind == "calculator":
                    st.iframe(CALC, height=345)
                elif kind == "paint":
                    st.iframe(PAINT, height=330)
                elif kind == "character map":
                    st.iframe(CHARMAP, height=300)
                elif kind == "image":
                    st.image(win["path"], width="stretch")
                elif kind == "explorer":
                    rows = win["rows"]
                    if rows:
                        df = pd.DataFrame(rows)[["name", "category", "size_h", "modified"]]
                        st.dataframe(df, hide_index=True, width="stretch", height=min(300, 38 + 35 * len(df)))
                    else:
                        st.caption("Empty folder")
                else:
                    st.code(win.get("content", "")[:20000], language=None)

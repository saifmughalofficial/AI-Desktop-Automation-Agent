"""Visual theme: neon HUD stylesheet plus the animated header and neural-core canvases."""
from __future__ import annotations

import html
import json

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;800&family=Rajdhani:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
:root{--bg:#020817;--panel:rgba(7,24,52,.80);--line:rgba(56,189,248,.26);--line2:rgba(34,211,238,.62);
--cyan:#22d3ee;--sky:#38bdf8;--blue:#3b82f6;--text:#d6ecff;--muted:#7ea6cc;--green:#34d399;--amber:#fbbf24;
--red:#f87171;--violet:#a78bfa;--pink:#f472b6}
html,body,.stApp{font-family:'Rajdhani',system-ui,sans-serif}
.stApp{background:radial-gradient(1100px 520px at 50% -12%,rgba(34,211,238,.16),transparent 62%),
radial-gradient(800px 480px at 105% 105%,rgba(59,130,246,.14),transparent 60%),
radial-gradient(700px 420px at -5% 60%,rgba(167,139,250,.07),transparent 60%),linear-gradient(180deg,#020817,#030c20 60%,#020817);color:var(--text)}
.stApp:before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
background-image:linear-gradient(rgba(56,189,248,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(56,189,248,.045) 1px,transparent 1px);
background-size:44px 44px;-webkit-mask-image:radial-gradient(ellipse at 50% 30%,#000 30%,transparent 80%);mask-image:radial-gradient(ellipse at 50% 30%,#000 30%,transparent 80%);animation:gridDrift 30s linear infinite}
@keyframes gridDrift{to{background-position:44px 44px,44px 44px}}
header[data-testid="stHeader"]{background:transparent}
[data-testid="stMainBlockContainer"],.block-container{padding-top:1rem;padding-bottom:3rem;max-width:1560px}
h1,h2,h3,h4{font-family:'Orbitron',sans-serif!important;letter-spacing:.06em;color:#e6f6ff}
h1{font-size:1.45rem!important}h2{font-size:1.15rem!important}h3{font-size:1rem!important}
p,li,label,span,div{letter-spacing:.01em}
code{font-family:'JetBrains Mono',monospace!important;color:#7dd3fc!important;background:rgba(14,165,233,.10)!important}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#041029 0%,#020817 100%);border-right:1px solid var(--line)}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a,section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"]{border-radius:8px;margin:2px 6px;transition:all .2s;border:1px solid transparent}
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"]:hover{background:rgba(34,211,238,.08);border-color:var(--line)}
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"][aria-current="page"]{background:linear-gradient(90deg,rgba(34,211,238,.18),rgba(59,130,246,.06));border-color:var(--line2);box-shadow:0 0 18px rgba(34,211,238,.18)}
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"] span:not([data-testid="stIconMaterial"]){font-family:'Rajdhani';font-weight:600;letter-spacing:.08em;text-transform:uppercase;font-size:.9rem}
.stButton button,.stDownloadButton button,.stFormSubmitButton button,[data-testid="stPopover"] button{
background:linear-gradient(180deg,rgba(10,36,72,.85),rgba(5,20,44,.85));border:1px solid var(--line2);color:var(--text);
font-family:'Rajdhani';font-weight:700;letter-spacing:.09em;text-transform:uppercase;border-radius:9px;transition:all .18s ease;
box-shadow:inset 0 0 14px rgba(34,211,238,.08),0 0 0 rgba(0,0,0,0)}
.stButton button:hover,.stDownloadButton button:hover,.stFormSubmitButton button:hover{border-color:var(--cyan);color:#fff;
box-shadow:0 0 18px rgba(34,211,238,.35),inset 0 0 16px rgba(34,211,238,.16);transform:translateY(-1px)}
.stButton button:active{transform:translateY(0) scale(.98)}
.stButton button:disabled{opacity:.38;transform:none;box-shadow:none}
button[data-testid="stBaseButton-primary"],button[kind="primary"]{background:linear-gradient(90deg,#0891b2,#2563eb)!important;border:1px solid #67e8f9!important;color:#fff!important;
box-shadow:0 0 22px rgba(34,211,238,.35)!important;position:relative;overflow:hidden}
button[data-testid="stBaseButton-primary"]:after{content:"";position:absolute;top:0;left:-60%;width:40%;height:100%;
background:linear-gradient(90deg,transparent,rgba(255,255,255,.28),transparent);transform:skewX(-20deg);animation:sheen 3.4s ease-in-out infinite}
@keyframes sheen{0%,60%{left:-60%}100%{left:130%}}
.stop-btn button{background:linear-gradient(90deg,#b91c1c,#e11d48)!important;border-color:#fca5a5!important;color:#fff!important;box-shadow:0 0 22px rgba(244,63,94,.45)!important;animation:stopPulse 1.6s ease-in-out infinite}
@keyframes stopPulse{50%{box-shadow:0 0 34px rgba(244,63,94,.75)}}
div[data-baseweb="input"],div[data-baseweb="textarea"],div[data-baseweb="select"]>div,div[data-baseweb="base-input"]{
background:rgba(3,14,34,.88)!important;border-color:var(--line)!important;border-radius:9px!important}
div[data-baseweb="input"]:focus-within,div[data-baseweb="textarea"]:focus-within{border-color:var(--cyan)!important;box-shadow:0 0 0 1px var(--cyan),0 0 22px rgba(34,211,238,.28)!important}
input,textarea{color:#e8f6ff!important;font-family:'Rajdhani'!important;font-size:1.02rem!important;font-weight:500!important}
.cmd-box div[data-baseweb="input"]{min-height:52px;background:linear-gradient(90deg,rgba(4,18,42,.95),rgba(6,26,58,.9))!important;border:1px solid var(--line2)!important;
box-shadow:0 0 26px rgba(34,211,238,.14),inset 0 0 18px rgba(34,211,238,.06)!important}
.cmd-box input{font-size:1.12rem!important;letter-spacing:.02em}
[data-testid="stExpander"]{background:var(--panel);border:1px solid var(--line);border-radius:10px}
[data-testid="stExpander"] summary{font-family:'Rajdhani';font-weight:700;letter-spacing:.06em}
[data-testid="stTabs"] [role="tab"]{font-family:'Rajdhani';font-weight:700;letter-spacing:.08em;text-transform:uppercase}
[data-testid="stTabs"] [role="tab"][aria-selected="true"]{color:var(--cyan)}
[data-testid="stMetric"]{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
[data-testid="stMetricValue"]{font-family:'Orbitron';color:#e6f6ff}
[data-testid="stAlert"]{border-radius:10px;border:1px solid var(--line)}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:10px;overflow:hidden}
[data-testid="stProgress"]>div>div>div>div{background:linear-gradient(90deg,#22d3ee,#3b82f6)!important}
[data-testid="stDialog"] div[role="dialog"]{background:linear-gradient(180deg,#071a3a,#030c20)!important;border:1px solid var(--line2);box-shadow:0 0 60px rgba(34,211,238,.25)}
[data-testid="stPills"] button,[data-testid="stButtonGroup"] button{border-radius:999px!important}
/* ---------------------------------------------------------------- HUD panels */
.hud{position:relative;background:linear-gradient(180deg,rgba(8,30,64,.80),rgba(3,14,34,.86));border:1px solid var(--line);border-radius:11px;
padding:12px 14px 13px;margin-bottom:14px;box-shadow:inset 0 0 0 1px rgba(34,211,238,.04),0 12px 32px rgba(0,0,0,.38),0 0 26px rgba(34,211,238,.06);
overflow:hidden;animation:hudIn .55s cubic-bezier(.2,.8,.2,1) both}
.hud:after{content:"";position:absolute;inset:0;pointer-events:none;background:linear-gradient(115deg,transparent 40%,rgba(125,211,252,.07) 50%,transparent 60%);
background-size:250% 100%;animation:sweep 7s linear infinite}
@keyframes sweep{0%{background-position:150% 0}100%{background-position:-100% 0}}
@keyframes hudIn{from{opacity:0;transform:translateY(10px) scale(.99)}to{opacity:1;transform:none}}
.hud .cn{position:absolute;width:12px;height:12px;border-color:var(--cyan);border-style:solid;opacity:.9;filter:drop-shadow(0 0 4px var(--cyan))}
.hud .c1{top:-1px;left:-1px;border-width:2px 0 0 2px;border-top-left-radius:10px}.hud .c2{top:-1px;right:-1px;border-width:2px 2px 0 0;border-top-right-radius:10px}
.hud .c3{bottom:-1px;left:-1px;border-width:0 0 2px 2px;border-bottom-left-radius:10px}.hud .c4{bottom:-1px;right:-1px;border-width:0 2px 2px 0;border-bottom-right-radius:10px}
.hud-t{display:flex;align-items:center;gap:8px;font-family:'Orbitron';font-size:.70rem;font-weight:700;letter-spacing:.16em;color:#c4ecff;text-transform:uppercase;margin-bottom:10px}
.hud-t svg{width:15px;height:15px;stroke:var(--cyan);fill:none;stroke-width:2;filter:drop-shadow(0 0 4px rgba(34,211,238,.6))}
.hud-t .tail{margin-left:auto;display:flex;gap:4px}.hud-t .tail i{width:4px;height:4px;border-radius:50%;background:var(--cyan);opacity:.35;animation:blink 1.6s infinite}
.hud-t .tail i:nth-child(2){animation-delay:.25s}.hud-t .tail i:nth-child(3){animation-delay:.5s}
@keyframes blink{50%{opacity:1;box-shadow:0 0 6px var(--cyan)}}
.hud-t .meta{margin-left:auto;font-family:'Rajdhani';font-size:.78rem;letter-spacing:.06em;color:var(--muted);text-transform:none}
/* gauges */
.gauges{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}
.gauge{position:relative;text-align:center}
.gauge svg{width:100%;max-width:104px;height:auto;display:block;margin:0 auto;overflow:visible}
.g-track{fill:none;stroke:rgba(56,189,248,.12);stroke-width:7}
.g-ticks{fill:none;stroke:rgba(125,211,252,.35);stroke-width:2;stroke-dasharray:1 5.2}
.g-val{fill:none;stroke-width:7;stroke-linecap:round;transition:stroke-dashoffset 1.1s cubic-bezier(.2,.8,.2,1),stroke .4s}
.g-ring{fill:none;stroke-width:1;opacity:.5;transform-origin:50% 50%;animation:spin 9s linear infinite;stroke-dasharray:4 10}
@keyframes spin{to{transform:rotate(360deg)}}
.g-lbl{font-family:'Orbitron';font-size:7.5px;fill:#9fd8f5;letter-spacing:1.5px}
.g-num{font-family:'Orbitron';font-size:15px;font-weight:800;fill:#eaf8ff}
.g-sub{font-size:.74rem;color:var(--muted);margin-top:2px}
/* charts */
.chart{margin-bottom:9px}.chart:last-child{margin-bottom:0}
.chart-h{display:flex;justify-content:space-between;font-size:.84rem;font-weight:600;color:#bfe3f7;margin-bottom:2px}
.chart-h b{font-family:'Orbitron';font-size:.78rem;color:#fff}
.chart svg{width:100%;height:46px;display:block}
.chart .ln{fill:none;stroke-width:1.8;filter:drop-shadow(0 0 3px currentColor)}
.chart .dot{animation:dotPulse 1.4s ease-in-out infinite}
@keyframes dotPulse{50%{r:4.5;opacity:.6}}
/* data flow */
.flow svg{width:100%;height:auto;display:block}
.flow .wire{fill:none;stroke:rgba(56,189,248,.35);stroke-width:1.4}
.flow .pulse{fill:none;stroke:var(--cyan);stroke-width:2;stroke-dasharray:6 14;animation:flowDash 1.2s linear infinite;filter:drop-shadow(0 0 3px var(--cyan))}
@keyframes flowDash{to{stroke-dashoffset:-20}}
.flow .node rect{fill:rgba(8,32,70,.9);stroke:rgba(56,189,248,.55);stroke-width:1.2;rx:6}
.flow .node text{font-family:'Rajdhani';font-size:10.5px;font-weight:700;fill:#d6ecff;letter-spacing:.6px}
.flow .node.on rect{stroke:var(--cyan);fill:rgba(14,116,144,.55);filter:drop-shadow(0 0 7px rgba(34,211,238,.9));animation:nodeGlow 1.1s ease-in-out infinite}
@keyframes nodeGlow{50%{filter:drop-shadow(0 0 14px rgba(34,211,238,1))}}
.status-line{display:flex;align-items:center;gap:8px;font-size:.88rem;font-weight:600;color:#bfe3f7;margin-top:8px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green);animation:breathe 1.8s ease-in-out infinite}
.dot.amber{background:var(--amber);box-shadow:0 0 8px var(--amber)}.dot.red{background:var(--red);box-shadow:0 0 8px var(--red)}.dot.off{background:#475569;box-shadow:none;animation:none}
@keyframes breathe{50%{opacity:.45;transform:scale(.8)}}
/* agent rows */
.agent{display:grid;grid-template-columns:22px 1fr auto;align-items:center;gap:8px;padding:6px 8px;border-radius:8px;margin-bottom:5px;
background:linear-gradient(90deg,rgba(14,46,90,.45),rgba(6,22,48,.25));border:1px solid rgba(56,189,248,.12);transition:border-color .2s}
.agent:hover{border-color:var(--line2)}
.agent svg{width:18px;height:18px;stroke:var(--sky);fill:none;stroke-width:1.8}
.agent .nm{font-weight:700;font-size:.92rem;color:#e2f3ff;line-height:1.1}.agent .ds{font-size:.74rem;color:var(--muted);line-height:1.1}
.agent .st{display:flex;align-items:center;gap:6px;font-size:.78rem;font-weight:700;letter-spacing:.04em}
.bar{height:4px;border-radius:4px;background:rgba(56,189,248,.12);overflow:hidden;margin-top:4px}
.bar i{display:block;height:100%;border-radius:4px;background:linear-gradient(90deg,var(--cyan),var(--blue));box-shadow:0 0 8px var(--cyan);transition:width .8s ease}
.bar.run i{background:linear-gradient(90deg,var(--amber),#fb923c);box-shadow:0 0 8px var(--amber);background-size:200% 100%;animation:barFlow 1.2s linear infinite}
@keyframes barFlow{to{background-position:-200% 0}}
/* terminal */
.term{font-family:'JetBrains Mono',monospace;font-size:.74rem;line-height:1.5;background:rgba(1,8,22,.9);border:1px solid rgba(56,189,248,.18);
border-radius:8px;padding:9px 11px;height:196px;overflow:hidden;position:relative;display:flex;flex-direction:column;justify-content:flex-end}
.term:before{content:"";position:absolute;inset:0;background:repeating-linear-gradient(0deg,rgba(255,255,255,.018) 0 1px,transparent 1px 3px);pointer-events:none}
.term .l{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#a5d8f3}
.term .p{color:var(--cyan)}.term .t{color:#4b6b8c}.term .OK{color:var(--green)}.term .FAIL{color:var(--red)}.term .WARN{color:var(--amber)}
.term .RUN{color:#7dd3fc}.term .SIM{color:var(--violet)}.term .DONE{color:#fff;font-weight:600}.term .SKIP{color:#94a3b8}
.term .cur{display:inline-block;width:7px;height:13px;background:var(--cyan);vertical-align:-2px;animation:cursor 1s steps(1) infinite;box-shadow:0 0 6px var(--cyan)}
@keyframes cursor{50%{opacity:0}}
/* storage */
.store{display:grid;grid-template-columns:96px 1fr;gap:12px;align-items:center}
.store svg{width:96px;height:96px}
.store .kv{font-size:.86rem;color:#bfe3f7;line-height:1.55}.store .kv b{font-family:'Orbitron';font-size:.82rem;color:#fff}
/* tasks */
.task{margin-bottom:8px}.task .hd{display:flex;justify-content:space-between;gap:8px;font-size:.86rem;font-weight:600;color:#d6ecff}
.task .hd span:first-child{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.empty{color:var(--muted);font-size:.88rem;text-align:center;padding:14px 6px;border:1px dashed rgba(56,189,248,.22);border-radius:8px}
/* plan + steps */
.risk{display:inline-flex;align-items:center;gap:5px;padding:2px 9px;border-radius:999px;font-size:.72rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;border:1px solid}
.risk.low{color:#6ee7b7;border-color:rgba(52,211,153,.5);background:rgba(16,185,129,.10)}
.risk.medium{color:#fcd34d;border-color:rgba(251,191,36,.5);background:rgba(245,158,11,.10)}
.risk.high{color:#fca5a5;border-color:rgba(248,113,113,.6);background:rgba(239,68,68,.12);animation:riskHi 1.6s ease-in-out infinite}
.risk.blocked{color:#f9a8d4;border-color:rgba(244,114,182,.6);background:rgba(236,72,153,.12)}
@keyframes riskHi{50%{box-shadow:0 0 12px rgba(248,113,113,.55)}}
.chip{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;font-size:.78rem;font-weight:700;letter-spacing:.06em;border:1px solid var(--line);color:#bfe3f7;background:rgba(8,30,64,.6);margin:0 6px 6px 0}
.plan-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:8px}
.plan-head .sum{font-family:'Orbitron';font-size:.86rem;color:#fff;letter-spacing:.05em}
table.steps{width:100%;border-collapse:separate;border-spacing:0 5px;font-size:.88rem}
table.steps th{font-family:'Orbitron';font-size:.62rem;letter-spacing:.14em;color:var(--muted);text-align:left;padding:2px 8px;font-weight:700}
table.steps td{background:rgba(8,30,64,.55);padding:7px 8px;border-top:1px solid rgba(56,189,248,.12);border-bottom:1px solid rgba(56,189,248,.12);vertical-align:top;color:#dcefff}
table.steps td:first-child{border-left:1px solid rgba(56,189,248,.12);border-radius:8px 0 0 8px;font-family:'Orbitron';font-size:.72rem;color:var(--cyan)}
table.steps td:last-child{border-right:1px solid rgba(56,189,248,.12);border-radius:0 8px 8px 0}
table.steps tr{animation:hudIn .45s ease both}
table.steps .sub{font-size:.76rem;color:var(--muted);margin-top:2px}
table.steps .warn{font-size:.78rem;color:#fcd34d;margin-top:3px}.table.steps .bad{color:#fca5a5}
table.steps .bad{font-size:.78rem;color:#fca5a5;margin-top:3px;font-weight:600}
.callout{border-radius:10px;padding:10px 13px;margin:8px 0;font-size:.92rem;border:1px solid}
.callout.info{background:rgba(14,116,144,.16);border-color:rgba(34,211,238,.35);color:#cdefff}
.callout.warn{background:rgba(180,83,9,.16);border-color:rgba(251,191,36,.42);color:#fde7b0}
.callout.bad{background:rgba(153,27,27,.20);border-color:rgba(248,113,113,.5);color:#fecaca}
.callout.ok{background:rgba(6,95,70,.20);border-color:rgba(52,211,153,.45);color:#c9f7e4}
.callout b{color:#fff}
.srow{display:grid;grid-template-columns:26px 1fr auto;gap:8px;align-items:start;padding:7px 9px;border-radius:9px;margin-bottom:5px;
background:rgba(8,30,64,.5);border:1px solid rgba(56,189,248,.12);transition:all .3s}
.srow.running{border-color:var(--cyan);box-shadow:0 0 16px rgba(34,211,238,.25);background:rgba(14,116,144,.25)}
.srow.paused{border-color:var(--amber);box-shadow:0 0 16px rgba(251,191,36,.25)}
.srow .ic{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;font-size:.72rem;font-weight:800;border:1.5px solid #335; color:#94a3b8}
.srow .ic.success{border-color:var(--green);color:var(--green);box-shadow:0 0 8px rgba(52,211,153,.5)}
.srow .ic.unverified{border-color:var(--amber);color:var(--amber)}
.srow .ic.failed{border-color:var(--red);color:var(--red);box-shadow:0 0 8px rgba(248,113,113,.5)}
.srow .ic.simulated{border-color:var(--violet);color:var(--violet)}
.srow .ic.skipped,.srow .ic.cancelled{border-color:#64748b;color:#94a3b8}
.srow .ic.running{border-color:var(--cyan);border-top-color:transparent;animation:spin .8s linear infinite}
.srow .ic.paused{border-color:var(--amber);color:var(--amber);animation:breathe 1.2s infinite}
.srow .d{font-size:.9rem;color:#e2f3ff;font-weight:600}.srow .m{font-size:.8rem;color:var(--muted);margin-top:1px}
.srow .s{font-size:.7rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.prog{height:8px;border-radius:8px;background:rgba(56,189,248,.12);overflow:hidden;margin:6px 0 10px}
.prog i{display:block;height:100%;background:linear-gradient(90deg,#22d3ee,#3b82f6,#22d3ee);background-size:200% 100%;animation:barFlow 1.4s linear infinite;box-shadow:0 0 10px var(--cyan);transition:width .5s ease}
.prog.done i{animation:none;background:linear-gradient(90deg,#10b981,#22d3ee)}
.page-title{display:flex;align-items:center;gap:12px;margin:2px 0 14px}
.page-title .ico{width:38px;height:38px;border-radius:10px;display:grid;place-items:center;background:linear-gradient(135deg,rgba(34,211,238,.25),rgba(59,130,246,.15));border:1px solid var(--line2);box-shadow:0 0 18px rgba(34,211,238,.25)}
.page-title .ico svg{width:20px;height:20px;stroke:var(--cyan);fill:none;stroke-width:2}
.page-title h1{margin:0!important;padding:0!important}
.page-title .sub{font-size:.9rem;color:var(--muted);margin-top:-2px}
.appcard{position:relative;padding:14px;border-radius:12px;border:1px solid var(--line);background:linear-gradient(160deg,rgba(10,40,84,.7),rgba(3,14,34,.9));margin-bottom:8px;transition:all .25s}
.appcard:hover{border-color:var(--line2);box-shadow:0 0 22px rgba(34,211,238,.18);transform:translateY(-2px)}
.appcard .nm{font-family:'Orbitron';font-size:.86rem;color:#fff;letter-spacing:.06em}.appcard .cmd{font-family:'JetBrains Mono';font-size:.72rem;color:var(--muted);margin-top:4px}
.appcard svg.big{width:30px;height:30px;stroke:var(--cyan);fill:none;stroke-width:1.6;filter:drop-shadow(0 0 6px rgba(34,211,238,.6));margin-bottom:6px}
.side-brand{display:flex;align-items:center;gap:10px;padding:4px 4px 12px;border-bottom:1px solid var(--line);margin-bottom:8px}
.side-brand svg{width:34px;height:34px}.side-brand b{font-family:'Orbitron';font-size:.78rem;letter-spacing:.12em;color:#e6f6ff;line-height:1.2}
.side-brand span{display:block;font-size:.72rem;color:var(--muted);letter-spacing:.08em}
.side-stat{font-size:.82rem;color:#bfe3f7;padding:5px 2px;display:flex;justify-content:space-between;border-bottom:1px dashed rgba(56,189,248,.12)}
.side-stat b{color:#fff}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin-bottom:10px}.tiles.t3{grid-template-columns:repeat(3,1fr)}
.tile{border:1px solid rgba(129,140,248,.25);border-radius:9px;padding:7px 8px;background:rgba(10,20,50,.55);text-align:center;transition:all .25s}
.tile:hover{border-color:var(--line2);box-shadow:0 0 14px var(--glow2)}
.tile b{display:block;font-family:'Orbitron';font-size:1.02rem;color:#fff;text-shadow:0 0 10px var(--glow1)}
.tile span{font-size:.72rem;color:var(--muted);letter-spacing:.06em;text-transform:uppercase}
.tile.ok b{color:#6ee7b7}.tile.warn b{color:#fcd34d}.tile.bad b{color:#fb7185}.tile.vi b{color:#c4b5fd}
.swatch{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:7px;vertical-align:1px}
.mini-h{font-family:'Orbitron';font-size:.6rem;letter-spacing:.16em;color:var(--muted);margin:8px 0 4px;text-transform:uppercase}
.mini{font-size:.82rem;color:#cfe3f7;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.mini em{color:var(--muted);font-style:normal}
.vd-title{font-family:'Orbitron';font-size:.74rem;letter-spacing:.1em;color:#e6f6ff;display:flex;align-items:center;gap:9px}
.vd-dots{display:inline-flex;gap:4px}.vd-dots i{width:9px;height:9px;border-radius:50%;background:#ff2d55;box-shadow:0 0 6px #ff2d55}
.vd-dots i:nth-child(2){background:#fbbf24;box-shadow:0 0 6px #fbbf24}.vd-dots i:nth-child(3){background:#34d399;box-shadow:0 0 6px #34d399}
[data-testid="stVerticalBlockBorderWrapper"]{background:rgba(6,14,36,.72);border-color:rgba(168,85,247,.35)!important;backdrop-filter:blur(6px);animation:hudIn .45s ease both}
.gauges:has(.gauge:nth-child(4)){grid-template-columns:repeat(4,1fr)}
.core-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:4px 14px}
.v-orb-wrap{display:flex;flex-direction:column;align-items:center;padding:10px 0 6px}
.v-orb{position:relative;width:138px;height:138px;border-radius:50%;display:grid;place-items:center;background:radial-gradient(circle at 35% 30%,rgba(56,189,248,.55),rgba(124,58,237,.35) 45%,rgba(225,29,72,.25) 70%,transparent 72%);box-shadow:0 0 40px rgba(56,189,248,.35),0 0 70px rgba(255,45,85,.18) inset;animation:vPulse 2.6s ease-in-out infinite}
.v-orb svg{width:46px;height:46px;fill:none;stroke:#e6f6ff;stroke-width:1.8;filter:drop-shadow(0 0 8px #38bdf8)}
.v-orb i{position:absolute;inset:-8px;border-radius:50%;border:1.5px solid rgba(56,189,248,.45);animation:vRing 3s linear infinite}
.v-orb i:nth-child(2){inset:-18px;border-color:rgba(168,85,247,.4);animation-delay:1s;border-style:dashed}
.v-orb i:nth-child(3){inset:-28px;border-color:rgba(255,45,85,.35);animation-delay:2s}
.v-wave{display:flex;gap:3px;height:34px;align-items:center;margin-top:30px}
.v-wave i{width:4px;height:8px;border-radius:3px;background:linear-gradient(#38bdf8,#ff2d55);animation:vBar 1.1s ease-in-out infinite}
.v-cap{font-family:Rajdhani;color:#9cc8e6;font-size:.9rem;margin-top:6px;letter-spacing:.04em}
@keyframes vPulse{50%{transform:scale(1.05);box-shadow:0 0 60px rgba(56,189,248,.5),0 0 90px rgba(255,45,85,.25) inset}}
@keyframes vRing{0%{transform:scale(.9) rotate(0);opacity:.9}100%{transform:scale(1.25) rotate(360deg);opacity:0}}
@keyframes vBar{0%,100%{height:6px}50%{height:30px}}
.manual h2{margin-top:1.4rem!important}
.manual table{width:100%;border-collapse:collapse;font-size:.9rem}.manual td,.manual th{border:1px solid rgba(56,189,248,.18);padding:6px 9px}
.manual th{background:rgba(14,116,144,.25);font-family:'Rajdhani';letter-spacing:.06em}
@media (max-width:900px){.gauges{grid-template-columns:repeat(3,1fr)}.store{grid-template-columns:80px 1fr}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

STATIC_CSS = """
*{animation:none!important;transition:none!important}
"""

# Glass panels over the live circuit-board background (shared by both palettes).
FX_CSS = """
html,body{background:#02040c}
.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"],[data-testid="stHeader"],[data-testid="stBottomBlockContainer"]{background:transparent!important}
[data-testid="stAppViewContainer"]{position:relative;z-index:1}
.stApp:before{opacity:.55}
[data-testid="stElementContainer"]:has(#agent-fx-marker),.element-container:has(#agent-fx-marker){display:none}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,rgba(4,10,30,.86),rgba(2,4,12,.92))!important;backdrop-filter:blur(10px)}
.hud{background:linear-gradient(180deg,rgba(8,20,48,.72),rgba(3,8,24,.80));backdrop-filter:blur(7px);-webkit-backdrop-filter:blur(7px);transition:transform .25s ease,box-shadow .25s ease,border-color .25s}
.hud:hover{transform:translateY(-2px);border-color:var(--line2);box-shadow:0 16px 40px rgba(0,0,0,.45),0 0 26px var(--glow1),0 0 40px var(--glow2)}
.hud:before{content:"";position:absolute;left:0;right:0;top:0;height:1.5px;background:linear-gradient(90deg,transparent,var(--sky),var(--hot),transparent);
background-size:200% 100%;animation:topline 4.5s linear infinite;opacity:.9}
@keyframes topline{to{background-position:-200% 0}}
.hud .c2,.hud .c4{border-color:var(--hot);filter:drop-shadow(0 0 5px var(--hot))}
[data-testid="stMetric"],[data-testid="stExpander"],.appcard{backdrop-filter:blur(6px);background:rgba(6,16,40,.72)}
#agent-boot{position:fixed;inset:0;z-index:999999;display:grid;place-items:center;cursor:pointer;
background:radial-gradient(ellipse at 30% 40%,rgba(37,99,235,.35),transparent 55%),radial-gradient(ellipse at 75% 60%,rgba(225,29,72,.32),transparent 55%),#02040c;
transition:opacity .7s ease,visibility .7s}
#agent-boot.out{opacity:0;visibility:hidden}
#agent-boot .box{width:min(560px,88vw);font-family:'JetBrains Mono',monospace;color:#bfe3f7;font-size:13px}
#agent-boot .t{font-family:'Orbitron',sans-serif;font-weight:800;letter-spacing:.22em;font-size:clamp(16px,2.6vw,26px);text-align:center;margin-bottom:22px;
background:linear-gradient(90deg,#7dd3fc,#c084fc,#fb7185,#7dd3fc);background-size:200% 100%;-webkit-background-clip:text;background-clip:text;color:transparent;animation:topline 3s linear infinite}
#agent-boot .ln{opacity:0;transform:translateX(-6px);animation:bootLn .35s ease forwards;margin:3px 0}
#agent-boot .ln b{color:#34d399}
@keyframes bootLn{to{opacity:1;transform:none}}
#agent-boot .pb{height:4px;border-radius:4px;background:rgba(148,163,184,.15);margin-top:18px;overflow:hidden}
#agent-boot .pb i{display:block;height:100%;width:0;background:linear-gradient(90deg,#38bdf8,#a855f7,#ff2d55);box-shadow:0 0 14px #a855f7;transition:width 2.3s cubic-bezier(.3,.7,.2,1)}
#agent-boot .sk{text-align:center;margin-top:12px;font-size:11px;color:#64748b;letter-spacing:.2em}
"""

PALETTES = {
    "dual": """:root{--hot:#ff2d55;--glow1:rgba(56,189,248,.18);--glow2:rgba(255,45,85,.14);--line:rgba(129,140,248,.28);--line2:rgba(244,63,94,.55)}
button[data-testid="stBaseButton-primary"],button[kind="primary"]{background:linear-gradient(90deg,#2563eb,#7c3aed 55%,#e11d48)!important;border-color:#f9a8d4!important;box-shadow:0 0 22px rgba(168,85,247,.45)!important}
.stButton button:hover,.stDownloadButton button:hover,.stFormSubmitButton button:hover{border-color:#fb7185;box-shadow:0 0 18px rgba(56,189,248,.30),0 0 26px rgba(255,45,85,.22),inset 0 0 16px rgba(168,85,247,.16)}
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"][aria-current="page"]{background:linear-gradient(90deg,rgba(56,189,248,.18),rgba(255,45,85,.12));border-color:rgba(244,63,94,.55);box-shadow:0 0 18px rgba(168,85,247,.25)}
.cmd-box div[data-baseweb="input"]{border-color:rgba(168,85,247,.6)!important;box-shadow:0 0 26px rgba(56,189,248,.14),0 0 30px rgba(255,45,85,.10),inset 0 0 18px rgba(168,85,247,.08)!important}
.prog i{background:linear-gradient(90deg,#38bdf8,#a855f7,#ff2d55,#38bdf8)}
.flow .pulse{stroke:url(#flowgrad)}
.page-title .ico{background:linear-gradient(135deg,rgba(56,189,248,.25),rgba(255,45,85,.18));border-color:rgba(244,63,94,.5)}
[data-testid="stTabs"] [role="tab"][aria-selected="true"]{color:#fb7185}""",
    "blue": """:root{--hot:#22d3ee;--glow1:rgba(34,211,238,.20);--glow2:rgba(59,130,246,.14)}""",
}


def fx_script(dual: bool, animate: bool, enabled: bool, roots: int, apps: int) -> str:
    """Live circuit-board background (+ one-time boot sequence) injected into the main page.

    Note: keep every '<' in this script followed by a space — Streamlit's sanitizer drops
    scripts containing '<' directly followed by a letter, digit or '/'. (tests/test_ui_safety.py)"""
    cfg = json.dumps({"dual": dual, "anim": animate, "on": enabled, "roots": roots, "apps": apps})
    return """<div id="agent-fx-marker"></div><script>
(function(){
var C = __CFG__;
var S = window.__agentFx = window.__agentFx || {};
S.dual = C.dual; S.anim = C.anim; S.on = C.on;
var doc = document;  // the app's own document (on Streamlit Cloud the app runs inside an iframe)
try { doc.body.dataset.palette = C.dual ? 'dual' : 'blue'; } catch (e) {}
var cv = doc.getElementById('agent-fx-bg');
if (cv) { cv.style.display = C.on ? 'block' : 'none'; if (S.redraw) S.redraw(); }
else if (C.on) { start(); }
boot();

function start(){
  cv = doc.createElement('canvas'); cv.id = 'agent-fx-bg';
  cv.style.cssText = 'position:fixed;inset:0;width:100vw;height:100vh;z-index:0;pointer-events:none;';
  doc.body.prepend(cv);
  var x = cv.getContext('2d'), W = 0, H = 0, bg = doc.createElement('canvas'), bx = bg.getContext('2d');
  var traces = [], pulses = [], bokeh = [], last = 0, t0 = performance.now();
  function rnd(a, b){ return a + Math.random() * (b - a); }
  function lerp(a, b, s){ return [a[0] + (b[0] - a[0]) * s | 0, a[1] + (b[1] - a[1]) * s | 0, a[2] + (b[2] - a[2]) * s | 0]; }
  function col(t){
    t = Math.max(0, Math.min(1, t));
    if (!S.dual) return lerp([34, 211, 238], [59, 130, 246], t);
    var A = [40, 120, 255], M = [176, 60, 255], B = [255, 38, 70];
    return t > 0.5 ? lerp(M, B, (t - 0.5) * 2) : lerp(A, M, t * 2);
  }
  function rgba(c, a){ return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a.toFixed(3) + ')'; }
  function build(){
    traces = []; pulses = []; bokeh = [];
    var n = Math.max(24, Math.round(W / 26));
    for (var i = 0; i !== n; i++) {
      var cx = rnd(-W * 0.4, W * 0.95), cy = H + rnd(0, H * 0.25), pts = [[cx, cy]];
      while (cy > -60 && cx < W + 60) {
        var r = Math.random(), len = rnd(30, 170);
        if (r > 0.45) { cx += len; cy -= len * 0.58; } else if (r > 0.18) { cx += len; } else { cy -= len * 0.6; }
        pts.push([cx, cy]);
      }
      var segs = [], tot = 0;
      for (var k = 1; k !== pts.length; k++) { var d = Math.hypot(pts[k][0] - pts[k-1][0], pts[k][1] - pts[k-1][1]); segs.push(d); tot += d; }
      traces.push({pts: pts, segs: segs, tot: tot, w: rnd(0.5, 1.7), a: rnd(0.10, 0.34), t: (pts[0][0] + W * 0.4) / (W * 1.35)});
    }
    for (var j = 0; j !== 34; j++) spawn();
    for (var b = 0; b !== 26; b++) bokeh.push({x: rnd(0, W), y: rnd(0, H), r: rnd(3, 16), a: rnd(0.10, 0.45), v: rnd(-0.12, 0.12), ph: rnd(0, 6.3)});
    bg.width = cv.width; bg.height = cv.height; bx.setTransform(x.getTransform());
    var g = bx.createLinearGradient(0, 0, W, H);
    g.addColorStop(0, S.dual ? '#020617' : '#020a1a'); g.addColorStop(0.55, S.dual ? '#07031a' : '#03102a'); g.addColorStop(1, S.dual ? '#14030b' : '#020817');
    bx.fillStyle = g; bx.fillRect(0, 0, W, H);
    traces.forEach(function(tr){
      var c = col(tr.t);
      bx.strokeStyle = rgba(c, tr.a); bx.lineWidth = tr.w; bx.beginPath(); bx.moveTo(tr.pts[0][0], tr.pts[0][1]);
      tr.pts.forEach(function(p){ bx.lineTo(p[0], p[1]); }); bx.stroke();
      tr.pts.forEach(function(p, idx){ if (idx % 2 === 1) { bx.fillStyle = rgba(c, tr.a * 1.6); bx.beginPath(); bx.arc(p[0], p[1], 1.7, 0, 6.3); bx.fill(); } });
    });
    var v = bx.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.25, W / 2, H / 2, Math.max(W, H) * 0.8);
    v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(0,0,0,0.65)'); bx.fillStyle = v; bx.fillRect(0, 0, W, H);
  }
  function spawn(){ var tr = traces[Math.floor(Math.random() * traces.length)]; pulses.push({tr: tr, d: rnd(0, tr.tot * 0.3), sp: rnd(1.2, 3.6), len: rnd(40, 120)}); }
  function at(tr, d){
    for (var k = 0; k !== tr.segs.length; k++) {
      if (d > tr.segs[k]) { d -= tr.segs[k]; continue; }
      var a = tr.pts[k], b = tr.pts[k + 1], s = d / tr.segs[k];
      return [a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s];
    }
    return tr.pts[tr.pts.length - 1];
  }
  function rs(){ var d = Math.min(1.5, window.devicePixelRatio || 1); W = doc.defaultView.innerWidth; H = doc.defaultView.innerHeight;
    cv.width = W * d; cv.height = H * d; x.setTransform(d, 0, 0, d, 0, 0); build(); frame(performance.now(), true); }
  function frame(now, force){
    if (!force && (!S.anim || doc.hidden)) return;
    if (!force && now - last > 33 === false) { requestAnimationFrame(frame); return; }
    last = now; var t = (now - t0) / 1000;
    x.drawImage(bg, 0, 0, W, H);
    x.globalCompositeOperation = 'lighter';
    bokeh.forEach(function(o){
      o.y += o.v; if (o.y > H + 20) o.y = -20; if (o.y + 20 > 0 === false) o.y = H + 20;
      var c = col(o.x / W), al = o.a * (0.6 + 0.4 * Math.sin(t * 0.8 + o.ph));
      var g = x.createRadialGradient(o.x, o.y, 0, o.x, o.y, o.r * 2.4);
      g.addColorStop(0, rgba(c, al)); g.addColorStop(1, rgba(c, 0)); x.fillStyle = g; x.beginPath(); x.arc(o.x, o.y, o.r * 2.4, 0, 6.3); x.fill();
    });
    for (var i = pulses.length - 1; i !== -1; i--) {
      var p = pulses[i], c = col(p.tr.t);
      if (S.anim) p.d += p.sp;
      for (var q = 0; q !== 9; q++) {
        var pt = at(p.tr, Math.max(0, p.d - q * p.len / 9));
        x.fillStyle = rgba(q === 0 ? [255, 255, 255] : c, (1 - q / 9) * 0.85);
        x.beginPath(); x.arc(pt[0], pt[1], q === 0 ? 2.2 : 1.8 - q * 0.12, 0, 6.3); x.fill();
      }
      var h = at(p.tr, p.d), hg = x.createRadialGradient(h[0], h[1], 0, h[0], h[1], 16);
      hg.addColorStop(0, rgba(c, 0.55)); hg.addColorStop(1, rgba(c, 0)); x.fillStyle = hg; x.beginPath(); x.arc(h[0], h[1], 16, 0, 6.3); x.fill();
      if (p.d - p.len > p.tr.tot) { pulses.splice(i, 1); spawn(); }
    }
    x.globalCompositeOperation = 'source-over';
    if (S.anim && !force) requestAnimationFrame(frame);
  }
  S.redraw = function(){ build(); frame(performance.now(), true); if (S.anim) requestAnimationFrame(frame); };
  doc.defaultView.addEventListener('resize', rs);
  doc.addEventListener('visibilitychange', function(){ if (!doc.hidden && S.anim) requestAnimationFrame(frame); });
  rs(); if (S.anim) requestAnimationFrame(frame);
}

function boot(){
  try { if (doc.defaultView.sessionStorage.getItem('agentBoot')) return; doc.defaultView.sessionStorage.setItem('agentBoot', '1'); } catch (e) { return; }
  if (!C.anim) return;
  var o = doc.createElement('div'); o.id = 'agent-boot';
  var box = doc.createElement('div'); box.className = 'box'; o.appendChild(box);
  var t = doc.createElement('div'); t.className = 't'; t.textContent = 'AI DESKTOP AUTOMATION AGENT'; box.appendChild(t);
  var lines = ['> initializing AI modules...', '> loading rules engine ............ OK', '> arming policy engine ............ OK',
               '> mounting sandbox: ' + C.roots + ' approved folder(s) .. OK', '> app allowlist: ' + C.apps + ' program(s) ...... OK',
               '> neural core online', '> all systems operational.'];
  lines.forEach(function(s, i){ var d = doc.createElement('div'); d.className = 'ln'; d.style.animationDelay = (0.18 + i * 0.27) + 's';
    if (s.slice(-2) === 'OK') { d.textContent = s.slice(0, -2); var b = doc.createElement('b'); b.textContent = 'OK'; d.appendChild(b); } else { d.textContent = s; }
    box.appendChild(d); });
  var pb = doc.createElement('div'); pb.className = 'pb'; var bar = doc.createElement('i'); pb.appendChild(bar); box.appendChild(pb);
  var sk = doc.createElement('div'); sk.className = 'sk'; sk.textContent = 'CLICK TO SKIP'; box.appendChild(sk);
  doc.body.appendChild(o);
  setTimeout(function(){ bar.style.width = '100%'; }, 60);
  function done(){ o.classList.add('out'); setTimeout(function(){ if (o.parentNode) o.parentNode.removeChild(o); }, 800); }
  o.addEventListener('click', done); setTimeout(done, 2700);
}
})();
</script>""".replace("__CFG__", cfg)


def header_html(mode_label: str, env_label: str, animations: bool, dual: bool = True) -> str:
    """Top bar (own iframe so the live clock can tick without Streamlit reruns)."""
    data = json.dumps({"mode": mode_label, "env": env_label, "anim": animations, "dual": dual})
    return """
<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@600;800&family=Rajdhani:wght@500;700&display=swap" rel="stylesheet">
<style>
html,body{margin:0;background:transparent;overflow:hidden;font-family:Rajdhani,system-ui,sans-serif;color:#d6ecff}
.bar{position:relative;height:66px;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;padding:0 16px;box-sizing:border-box;
border:1px solid rgba(56,189,248,.32);border-radius:12px;background:linear-gradient(180deg,rgba(8,32,70,.85),rgba(3,14,34,.9));
box-shadow:0 0 30px rgba(34,211,238,.12),inset 0 0 22px rgba(34,211,238,.06);overflow:hidden}
.bar:before{content:"";position:absolute;left:0;right:0;bottom:0;height:2px;background:linear-gradient(90deg,transparent,#22d3ee,#3b82f6,#22d3ee,transparent);
background-size:200% 100%;animation:line 4s linear infinite;opacity:.9}
@keyframes line{to{background-position:-200% 0}}
.left{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.chip{font-size:12px;font-weight:700;letter-spacing:.08em;padding:4px 10px;border-radius:999px;border:1px solid rgba(56,189,248,.4);background:rgba(8,40,80,.6);display:flex;gap:6px;align-items:center;white-space:nowrap}
.chip i{width:7px;height:7px;border-radius:50%;background:#34d399;box-shadow:0 0 8px #34d399;animation:b 1.8s infinite}
@keyframes b{50%{opacity:.4}}
.title{font-family:Orbitron;font-weight:800;font-size:20px;letter-spacing:.22em;text-align:center;white-space:nowrap;
background:linear-gradient(90deg,#a5f3fc,#e0f2fe,#7dd3fc,#a5f3fc);background-size:200% 100%;-webkit-background-clip:text;background-clip:text;color:transparent;
animation:shine 6s linear infinite;filter:drop-shadow(0 0 10px rgba(34,211,238,.55))}
@keyframes shine{to{background-position:-200% 0}}
.title small{display:block;font-family:Rajdhani;font-size:11px;letter-spacing:.42em;color:#7ea6cc;-webkit-text-fill-color:#7ea6cc;filter:none;margin-top:1px}
.right{display:flex;justify-content:flex-end;align-items:center;gap:14px}
.clock{font-family:Orbitron;font-size:19px;font-weight:600;color:#e6f6ff;text-shadow:0 0 12px rgba(34,211,238,.7);letter-spacing:.08em}
.date{font-size:12px;color:#7ea6cc;letter-spacing:.12em;text-align:right;line-height:1.2}
.ico{width:30px;height:30px;border-radius:8px;border:1px solid rgba(56,189,248,.35);display:grid;place-items:center;background:rgba(8,40,80,.5)}
.ico svg{width:16px;height:16px;stroke:#22d3ee;fill:none;stroke-width:2}
.noanim *{animation:none!important}
.dual .bar{border-color:rgba(168,85,247,.42);background:linear-gradient(90deg,rgba(10,30,80,.82),rgba(12,8,40,.86) 50%,rgba(50,6,22,.82))}
.dual .bar:before{background:linear-gradient(90deg,transparent,#38bdf8,#a855f7,#ff2d55,transparent);background-size:200% 100%}
.dual .title{background-image:linear-gradient(90deg,#7dd3fc,#e0f2fe,#fda4af,#c084fc,#7dd3fc)}
.dual .ico{border-color:rgba(255,45,85,.5)}.dual .ico svg{stroke:#fb7185}.dual .chip i{background:#fb7185;box-shadow:0 0 8px #fb7185}
@media (max-width:820px){.left .chip:nth-child(2){display:none}.title{font-size:14px;letter-spacing:.12em}.date{display:none}}
</style></head><body>
<div class="bar" id="bar">
 <div class="left"><span class="chip"><i></i><span id="mode"></span></span><span class="chip" id="env"></span></div>
 <div class="title">AI DESKTOP AUTOMATION AGENT<small>PLAN · APPROVE · EXECUTE · VERIFY</small></div>
 <div class="right"><div><div class="clock" id="clock">--:--:--</div></div><div class="date" id="date"></div>
  <div class="ico"><svg viewBox="0 0 24 24"><path d="M12 2l8 4v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6z"/><path d="M9 12l2 2 4-4"/></svg></div></div>
</div>
<script>
const D=__DATA__;
document.getElementById('mode').textContent=D.mode;document.getElementById('env').textContent=D.env;
if(!D.anim){document.getElementById('bar').classList.add('noanim');}if(D.dual){document.body.classList.add('dual');}
function pad(n){return String(n).padStart(2,'0');}
function tick(){const d=new Date();document.getElementById('clock').textContent=pad(d.getHours())+':'+pad(d.getMinutes())+':'+pad(d.getSeconds());
document.getElementById('date').innerHTML=d.toLocaleDateString(undefined,{weekday:'short'}).toUpperCase()+'<br>'+pad(d.getDate())+'/'+pad(d.getMonth()+1)+'/'+d.getFullYear();}
tick();setInterval(tick,1000);
</script></body></html>""".replace("__DATA__", data)


def brain_html(core_label: str, sub_label: str, animations: bool, height: int = 330, dual: bool = True) -> str:
    """Animated 3D neural-network 'AI core' (canvas, its own iframe so it never restarts on reruns)."""
    data = json.dumps({"label": core_label, "sub": sub_label, "anim": animations, "dual": dual})
    return f"""
<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@600;800&family=Rajdhani:wght@600&display=swap" rel="stylesheet">
<style>
html,body{{margin:0;height:100%;background:transparent;overflow:hidden}}
.wrap{{position:relative;height:{height}px;border:1px solid rgba(56,189,248,.28);border-radius:12px;overflow:hidden;
background:radial-gradient(ellipse at 50% 46%,rgba(14,116,144,.38),rgba(3,14,34,.2) 46%,rgba(2,8,23,.92) 75%),linear-gradient(180deg,rgba(6,24,52,.9),rgba(2,8,23,.96));
box-shadow:inset 0 0 40px rgba(34,211,238,.10),0 0 28px rgba(34,211,238,.10)}}
canvas{{position:absolute;inset:0;width:100%;height:100%}}
.dual .wrap{{background:radial-gradient(ellipse at 35% 46%,rgba(37,99,235,.34),transparent 45%),radial-gradient(ellipse at 66% 46%,rgba(225,29,72,.30),transparent 45%),linear-gradient(180deg,rgba(8,10,40,.92),rgba(2,4,14,.96));border-color:rgba(168,85,247,.42)}}
.dual .tag.r b{{color:#fb7185}}.dual .lbl{{background:linear-gradient(90deg,#7dd3fc,#c084fc,#fb7185);-webkit-background-clip:text;background-clip:text;color:transparent;text-shadow:none}}
.lbl{{position:absolute;left:0;right:0;bottom:12px;text-align:center;font-family:Orbitron,sans-serif;font-weight:800;letter-spacing:.32em;font-size:12px;color:#a5f3fc;text-shadow:0 0 12px rgba(34,211,238,.9)}}
.lbl small{{display:block;font-family:Rajdhani,sans-serif;font-weight:600;letter-spacing:.24em;font-size:10.5px;color:#7ea6cc;text-shadow:none;margin-top:3px}}
.tag{{position:absolute;top:10px;font-family:Rajdhani,sans-serif;font-weight:600;font-size:11px;letter-spacing:.18em;color:#7ea6cc}}
.tag.l{{left:14px}}.tag.r{{right:14px;text-align:right}}
.tag b{{color:#22d3ee;font-family:Orbitron;font-size:11px}}
</style></head><body><div class="wrap"><canvas id="c"></canvas>
<div class="tag l">NEURAL CORE<br><b id="fps">LIVE</b></div><div class="tag r">POLICY GUARD<br><b>ARMED</b></div>
<div class="lbl" id="lbl"></div></div>
<script>
const D={data};
document.getElementById('lbl').innerHTML=D.label+'<small>'+D.sub+'</small>';if(D.dual)document.body.classList.add('dual');
const c=document.getElementById('c'),x=c.getContext('2d');let W=0,H=0,DPR=1;
function rs(){{DPR=Math.min(2,window.devicePixelRatio||1);W=c.clientWidth;H=c.clientHeight;c.width=W*DPR;c.height=H*DPR;x.setTransform(DPR,0,0,DPR,0,0);}}
rs();window.addEventListener('resize',rs);
function rnd(a,b){{return a+Math.random()*(b-a);}}
const BL=[56,189,248],VI=[176,80,255],RD=[255,45,85];
function lp(a,b,s){{return [a[0]+(b[0]-a[0])*s|0,a[1]+(b[1]-a[1])*s|0,a[2]+(b[2]-a[2])*s|0];}}
function col(xn){{if(!D.dual)return BL;const t=Math.max(0,Math.min(1,(xn+1.05)/2.1));return t>.5?lp(VI,RD,(t-.5)*2):lp(BL,VI,t*2);}}
function cs(c,a){{return 'rgba('+c[0]+','+c[1]+','+c[2]+','+(+a).toFixed(3)+')';}}
const P=[];let guard=0;
while(P.length<300&&guard<40000){{guard++;
 const px=rnd(-1.05,1.05),py=rnd(-.85,.85),pz=rnd(-.7,.7);
 const side=px<0?-1:1;const cx=side*.5;
 const v=((px-cx)/.56)**2+(py/.80)**2+(pz/.66)**2;
 const fis=Math.abs(px)<.06;
 if(v<1&&v>.42&&!fis){{P.push({{x:px,y:py*(py>0?.92:1),z:pz,s:rnd(.8,2.1),ph:rnd(0,6.28)}});}}
}}
const E=[];
for(let i=0;i<P.length;i++){{let n=0;for(let j=i+1;j<P.length&&n<4;j++){{
 const dx=P[i].x-P[j].x,dy=P[i].y-P[j].y,dz=P[i].z-P[j].z;const d=dx*dx+dy*dy+dz*dz;
 if(d<.048){{E.push([i,j]);n++;}}}}}}
const adj=P.map(()=>[]);E.forEach((e,k)=>{{adj[e[0]].push(k);adj[e[1]].push(k);}});
const pulses=[];function spawn(){{const k=Math.floor(Math.random()*E.length);pulses.push({{k,t:0,dir:Math.random()<.5?1:-1,sp:rnd(.012,.03),life:6}});}}
for(let i=0;i<26;i++)spawn();
const traces=[];
for(let s of[-1,1])for(let i=0;i<5;i++){{const y=rnd(-.55,.55);traces.push({{s,y,k:rnd(.15,.3),off:rnd(0,1)}});}}
let t0=performance.now(),frames=0,last=t0;
function proj(p,a,R,cx,cy){{const ca=Math.cos(a),sa=Math.sin(a);const X=p.x*ca+p.z*sa,Z=-p.x*sa+p.z*ca;const k=1/(1+Z*.35);
 return [cx+X*R*k,cy+p.y*R*k,Z];}}
function draw(now){{
 const t=(now-t0)/1000;x.clearRect(0,0,W,H);
 const cx=W/2,cy=H*.44,R=Math.min(W*.30,H*.36);
 const a=D.anim?Math.sin(t*.35)*.55:0.25;
 // platform rings
 x.save();x.translate(cx,cy+R*1.08);x.scale(1,.26);
 for(let i=0;i<4;i++){{const r=R*(.55+i*.22);x.beginPath();x.arc(0,0,r,0,Math.PI*2);
  x.strokeStyle=cs(D.dual&&i%2?RD:BL,.42-i*.08);x.lineWidth=i===0?2:1;x.setLineDash(i%2?[6,10]:[]);x.lineDashOffset=D.anim?-t*30*(i%2?1:-1):0;x.stroke();}}
 const g=x.createRadialGradient(0,0,0,0,0,R*1.1);g.addColorStop(0,'rgba(34,211,238,.35)');g.addColorStop(1,'rgba(34,211,238,0)');x.fillStyle=g;x.beginPath();x.arc(0,0,R*1.1,0,Math.PI*2);x.fill();
 x.restore();x.setLineDash([]);
 // beam
 const bg=x.createLinearGradient(0,cy,0,cy+R*1.1);bg.addColorStop(0,'rgba(34,211,238,0)');bg.addColorStop(1,'rgba(34,211,238,.18)');
 x.fillStyle=bg;x.beginPath();x.moveTo(cx-R*.5,cy);x.lineTo(cx+R*.5,cy);x.lineTo(cx+R*.9,cy+R*1.08);x.lineTo(cx-R*.9,cy+R*1.08);x.closePath();x.fill();
 // circuit traces
 x.lineWidth=1.2;
 traces.forEach(tr=>{{const y=cy+tr.y*R;const xs=tr.s<0?0:W;const xe=cx+tr.s*R*(1.02+Math.abs(tr.y)*.2);const xm=xs+(xe-xs)*.55;
  x.strokeStyle=cs(tr.s<0?BL:col(1),.30);x.beginPath();x.moveTo(xs,y+tr.s*14);x.lineTo(xm,y+tr.s*14);x.lineTo(xm+(xe-xm)*.3,y);x.lineTo(xe,y);x.stroke();
  const u=((D.anim?t*tr.k:0)+tr.off)%1;const px=xs+(xe-xs)*u;const py=u<.55?y+tr.s*14:y;
  x.fillStyle=cs(tr.s<0?[103,232,249]:col(1),1);x.shadowColor=cs(tr.s<0?BL:col(1),1);x.shadowBlur=10;x.beginPath();x.arc(px,py,2,0,6.3);x.fill();x.shadowBlur=0;}});
 // core glow
 const cg=x.createRadialGradient(cx,cy,0,cx,cy,R*1.25);cg.addColorStop(0,D.dual?'rgba(168,85,247,.30)':'rgba(56,189,248,.30)');cg.addColorStop(.5,'rgba(34,211,238,.10)');cg.addColorStop(1,'rgba(34,211,238,0)');
 x.fillStyle=cg;x.beginPath();x.arc(cx,cy,R*1.25,0,Math.PI*2);x.fill();
 // orbit rings
 x.save();x.translate(cx,cy);
 for(let i=0;i<2;i++){{x.save();x.rotate((D.anim?t*(i?-.25:.18):0)+i);x.scale(1,.32+i*.1);x.beginPath();x.arc(0,0,R*(1.22+i*.12),0,Math.PI*2);
  x.strokeStyle='rgba(125,211,252,'+(.22-i*.06)+')';x.setLineDash([2,9]);x.lineWidth=1.3;x.stroke();x.restore();}}
 x.restore();x.setLineDash([]);
 const S=P.map(p=>proj(p,a,R,cx,cy));
 x.globalCompositeOperation='lighter';
 for(const [i,j] of E){{const A=S[i],B=S[j];const z=(A[2]+B[2])/2;const al=.10+.22*(1-(z+.7)/1.4);
  x.strokeStyle=cs(col((P[i].x+P[j].x)/2),al);x.lineWidth=.8;x.beginPath();x.moveTo(A[0],A[1]);x.lineTo(B[0],B[1]);x.stroke();}}
 for(let i=0;i<P.length;i++){{const s=S[i],p=P[i];const tw=.55+.45*Math.sin(t*2.2+p.ph);const z=(s[2]+.7)/1.4;
  const r=p.s*(1.25-z*.5);const c0=col(p.x);x.fillStyle=cs([c0[0]+(255-c0[0])*.45*tw|0,c0[1]+(255-c0[1])*.45*tw|0,c0[2]+(255-c0[2])*.45*tw|0],.35+.55*(1-z)*tw);x.beginPath();x.arc(s[0],s[1],r,0,6.3);x.fill();}}
 for(let q=pulses.length-1;q>=0;q--){{const pu=pulses[q];const [i,j]=E[pu.k];const A=pu.dir>0?S[i]:S[j],B=pu.dir>0?S[j]:S[i];
  const px=A[0]+(B[0]-A[0])*pu.t,py=A[1]+(B[1]-A[1])*pu.t;
  const gr=x.createRadialGradient(px,py,0,px,py,9);gr.addColorStop(0,'rgba(255,255,255,.95)');const pc=col(P[i].x);gr.addColorStop(.3,cs(pc,.75));gr.addColorStop(1,cs(pc,0));
  x.fillStyle=gr;x.beginPath();x.arc(px,py,9,0,6.3);x.fill();
  if(D.anim)pu.t+=pu.sp;
  if(pu.t>=1){{const end=pu.dir>0?j:i;const nx=adj[end];pu.life--;if(pu.life<=0||!nx.length){{pulses.splice(q,1);spawn();continue;}}
   const k=nx[Math.floor(Math.random()*nx.length)];pu.k=k;pu.dir=E[k][0]===end?1:-1;pu.t=0;}}}}
 x.globalCompositeOperation='source-over';
 frames++;if(now-last>1000){{document.getElementById('fps').textContent=frames+' FPS';frames=0;last=now;}}
 if(D.anim&&!document.hidden)requestAnimationFrame(draw);
}}
requestAnimationFrame(draw);
document.addEventListener('visibilitychange',()=>{{if(!document.hidden&&D.anim)requestAnimationFrame(draw);}});
</script></body></html>"""


def esc(s: object) -> str:
    return html.escape("" if s is None else str(s))

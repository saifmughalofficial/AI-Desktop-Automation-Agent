"""Browser hands-free voice: continuous listening with the browser's speech recognition (Chrome / Edge).

This is the only way a *website* can hear you without buttons — Python on a server cannot open your
microphone. The page listens continuously (after you allow the microphone once), sends each finished
phrase (with up to 5 alternatives) to Python, and speaks the reply. Everything after that — choosing the
right alternative, planning, the policy engine's risk decision, execution and the audit log — is the
same Python code as the offline engine (app.voice.listener)."""
from __future__ import annotations

import json
import time

import streamlit as st

from app.ui import state
from app.voice import i18n
from app.voice.listener import VoiceListener, build_vocab

CSS = """
.vroot{font-family:Rajdhani,system-ui,sans-serif;padding:9px 11px;border-radius:12px;margin:6px 0;
 border:1px solid rgba(56,189,248,.45);background:linear-gradient(135deg,rgba(14,40,90,.7),rgba(80,12,40,.5));
 box-shadow:0 0 18px rgba(56,189,248,.18);color:#e6f6ff}
.vroot .row{display:flex;align-items:center;gap:8px;font-weight:700;font-size:.88rem}
.vroot .dot{width:10px;height:10px;border-radius:50%;background:#64748b;flex:none}
.vroot.on .dot{background:#34d399;box-shadow:0 0 10px #34d399;animation:vp 1.2s ease-in-out infinite}
.vroot.speak .dot{background:#a855f7;box-shadow:0 0 10px #a855f7}
.vroot.err .dot{background:#f87171}.vroot.err{border-color:#f87171}
.vroot .heard{font-size:.8rem;color:#9cc8e6;min-height:1.1em;margin-top:4px;overflow:hidden;text-overflow:ellipsis;
 white-space:nowrap}
.vroot .bars{display:flex;gap:2px;align-items:flex-end;height:14px;margin-top:5px}
.vroot .bars i{flex:1;height:3px;border-radius:2px;background:linear-gradient(#38bdf8,#ff2d55)}
.vroot.on .bars i{animation:vb 1s ease-in-out infinite}
.vroot.on .bars i:nth-child(2n){animation-delay:.15s}.vroot.on .bars i:nth-child(3n){animation-delay:.3s}
@keyframes vp{50%{transform:scale(1.35);opacity:.6}}@keyframes vb{50%{height:14px}}
"""

JS = r"""
export default function(component) {
  const { data, setTriggerValue, parentElement } = component;
  const G = window.__agentVoice || (window.__agentVoice = {});
  G.send = setTriggerValue;
  let root = parentElement.querySelector('.vroot');
  if (!root) {
    root = document.createElement('div');
    root.className = 'vroot';
    root.innerHTML = '<div class="row"><span class="dot"></span><span class="st">Starting voice…</span></div>' +
      '<div class="heard"></div><div class="bars">' + '<i></i>'.repeat(16) + '</div>';
    parentElement.appendChild(root);
  }
  G.root = root;
  const status = (txt, cls) => { if (G.root) { G.root.className = 'vroot ' + (cls || ''); G.root.querySelector('.st').textContent = txt; } };
  const heard = (txt) => { if (G.root) G.root.querySelector('.heard').textContent = txt || ''; };
  if (G.lastStatus) status(G.lastStatus[0], G.lastStatus[1]);
  const setStatus = (t, c) => { G.lastStatus = [t, c]; status(t, c); };

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!data.enabled) {
    G.wanted = false;
    if (G.rec) { try { G.rec.abort(); } catch (e) {} }
    setStatus('Voice off', '');
    return;
  }
  if (!SR) { setStatus('This browser has no speech recognition — open the app in Chrome or Edge', 'err'); return; }
  G.wanted = true;
  G.lang = data.lang;

  const restart = () => {
    if (!G.wanted || G.running) return;
    if (G.speaking) { setTimeout(restart, 300); return; }
    try { G.rec.lang = G.lang; G.rec.start(); G.running = true; }
    catch (e) { setTimeout(restart, 800); }
  };
  if (!G.rec) {
    const rec = new SR();
    rec.continuous = true; rec.interimResults = true; rec.maxAlternatives = 5;
    rec.onstart = () => { G.running = true; setStatus('Listening — just speak', 'on'); };
    rec.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) {
          const alts = [];
          for (let j = 0; j < r.length; j++) { const t = (r[j].transcript || '').trim(); if (t) alts.push(t); }
          if (alts.length && !G.speaking) { heard(alts[0]); G.send('heard', { alts: alts, t: Date.now() }); }
        } else {
          heard((r[0].transcript || '') + ' …');
        }
      }
    };
    rec.onerror = (e) => {
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        G.wanted = false;
        setStatus('Microphone blocked — click the camera/mic icon in the address bar, allow it, then reload', 'err');
      } else if (e.error === 'audio-capture') {
        setStatus('No microphone found', 'err');
      }
    };
    rec.onend = () => { G.running = false; if (G.wanted) setTimeout(restart, 250); };
    G.rec = rec;
  }
  if (G.rec.lang !== G.lang && G.running) { try { G.rec.abort(); } catch (e) {} }
  restart();

  if (data.say && data.nonce && data.nonce !== G.lastNonce) {
    G.lastNonce = data.nonce;
    if (data.speak && 'speechSynthesis' in window) {
      const u = new SpeechSynthesisUtterance(data.say);
      u.lang = data.lang; u.rate = 1.05;
      G.speaking = true; setStatus('Speaking…', 'speak');
      try { G.rec.abort(); } catch (e) {}
      const done = () => { G.speaking = false; setStatus('Listening — just speak', 'on'); restart(); };
      u.onend = done; u.onerror = done;
      window.speechSynthesis.cancel(); window.speechSynthesis.speak(u);
    }
  }
}
"""

def _register():
    return st.components.v2.component("agent_web_voice", css=CSS, js=JS)


_component = _register()


def enabled() -> bool:
    s = state.svc()
    return bool(s.settings.voice_handsfree and (s.hosted or s.settings.voice_engine == "browser"))


def brain() -> VoiceListener:
    """Per-browser-session decision engine (same code path as the offline listener)."""
    s = state.svc()
    v = st.session_state.get("_web_voice")
    if v is None or v.svc is not s or v.lang != s.settings.voice_lang:
        v = VoiceListener()
        v.svc, v.lang = s, s.settings.voice_lang
        v.set_vocab(build_vocab(s) if v.lang.startswith("en") else [])
        st.session_state._web_voice = v
    v.on_say = lambda text: st.session_state.__setitem__("_web_say", (time.time(), text))
    return v


def mount() -> None:
    """Mount the always-on browser listener (sidebar, every page) and act on what it heard."""
    s = state.svc()
    on = enabled()
    say = st.session_state.get("_web_say")
    payload = {"enabled": on, "lang": i18n.BCP47.get(s.settings.voice_lang, "en-US"), "speak": s.settings.voice_speak,
               "say": say[1] if say else "", "nonce": f"{say[0]:.3f}" if say else ""}
    global _component
    with st.sidebar:
        try:
            result = _component(key="agent_web_voice", data=payload, on_heard_change=lambda: None)
        except st.errors.StreamlitAPIException:  # a fresh runtime (tests / server restart) forgot the registration
            _component = _register()
            result = _component(key="agent_web_voice", data=payload, on_heard_change=lambda: None)
    heard = getattr(result, "heard", None) if result is not None else None
    if not (on and heard):
        return
    try:
        alts = heard.get("alts") if isinstance(heard, dict) else json.loads(heard).get("alts")
    except Exception:
        alts = None
    if not alts:
        return
    v = brain()
    before = len(v.log)
    v.handle([str(a)[:300] for a in alts[:5]])
    for m in list(v.log)[before:]:
        state.push_event("INFO" if m["who"] != "ignored" else "WARN", f"Voice {m['who']}: {m['text'][:70]}")
    if v.nav_request:
        nav, v.nav_request = v.nav_request, None
        st.switch_page(st.session_state.pages[nav])
    if len(v.log) > before:
        st.rerun()  # redraw (new windows, run results) and let the page speak the reply

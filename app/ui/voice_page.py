"""Voice Assistant page — pure Python: st.audio_input → offline Vosk speech-to-text →
deterministic intent router → system answers / confirmations / agent plans →
offline text-to-speech played with st.audio."""
from __future__ import annotations

import hashlib
from datetime import datetime

import streamlit as st

from app.ui import components as C
from app.ui import state
from app.ui.system_page import _sys, confirm_dialog
from app.voice import i18n, stt, tts
from app.voice.assistant import HELP, VoiceAssistant
from app.ui import voice_hud

ORB = """<div class="v-orb-wrap{cls}"><div class="v-orb"><i></i><i></i><i></i>
<svg viewBox="0 0 24 24"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v4M8 22h8"/></svg></div>
<div class="v-wave">{bars}</div><div class="v-cap">{cap}</div></div>"""

QUICK = ["System status", "Top processes", "Battery", "Disk space", "Volume up", "Mute", "What time is it",
         "Open Notepad", "Organize my Downloads by type", "Go to history"]


def _lang() -> str:
    if "voice_lang" not in st.session_state:
        s = state.svc()
        st.session_state.voice_lang = "en" if s.hosted else s.settings.voice_lang
    return st.session_state.voice_lang


def _lang_changed() -> None:
    s = state.svc()
    if not s.hosted and st.session_state.voice_lang != s.settings.voice_lang:
        on = s.settings.voice_handsfree
        voice_hud.set_handsfree(on, st.session_state.voice_lang)


def log() -> list[dict]:
    return st.session_state.setdefault("voice_log", [])


def _speak(text: str) -> None:
    if st.session_state.get("voice_tts", True):
        st.session_state.voice_say = text


def process(text: str, source: str) -> None:
    s = state.svc()
    text = (text or "").strip()
    if not text:
        return
    reply = VoiceAssistant(_sys(), _lang()).handle(text)
    now = datetime.now().strftime("%H:%M:%S")
    log().append({"role": "user", "text": text, "t": now, "src": source})
    log().append({"role": "assistant", "text": reply.say, "t": now, "kind": reply.kind,
                  "heard": reply.heard})
    state.push_event("INFO", f"Voice ({source}): {text[:60]} → {reply.kind}")
    _speak(reply.say)
    if reply.kind == "confirm":
        st.session_state.voice_confirm = reply.data
    elif reply.kind == "stop":
        run = state.get_run()
        if run and not run.done:
            s.orchestrator.stop(run)
            state.push_event("WARN", f"Run {run.id}: STOP (voice).")
        else:
            log()[-1]["text"] = "Nothing is running right now."
            _speak("Nothing is running right now.")
    elif reply.kind == "navigate":
        st.session_state.voice_nav = reply.target
    elif reply.kind == "agent":
        state.queue_command(reply.target, "preview")
        if st.session_state.get("voice_auto_open", True):
            st.session_state.voice_nav = "command"


def play_pending() -> None:
    """Called from app.py on every page so spoken replies play even after navigation."""
    text = st.session_state.pop("voice_say", None)
    if not text:
        return
    audio = tts.synthesize(text, st.session_state.get("voice_rate", 1), _lang())
    if audio:
        with st.sidebar:
            st.caption("🔊 Assistant")
            st.audio(audio, format="audio/wav", autoplay=True)


def _model_box() -> bool:
    s = state.svc()
    if not stt.engine_available():
        st.markdown(C.callout("warn", "<b>Offline speech engine not installed.</b> Run <code>pip install vosk</code> "
                                      "(included in requirements.txt). You can still type to the assistant."),
                    unsafe_allow_html=True)
        return False
    lang = _lang()
    info = i18n.lang_info(lang)
    if stt.model_ready(s.voice_dir, lang):
        return True
    st.markdown(C.callout("info", f"<b>One-time setup:</b> download the free offline {info['name']} speech model "
                                  f"({info['model']}, ~{info['mb']} MB). After that, speech is recognised on this machine "
                                  "and no audio is sent anywhere."), unsafe_allow_html=True)
    if st.button(f"Download {info['name']} speech model", type="primary", icon=":material/download:"):
        bar = st.progress(0.0, "Downloading…")
        try:
            stt.download_model(s.voice_dir, lambda f: bar.progress(min(f, 1.0), f"Downloading… {f * 100:.0f}%"), lang)
            st.success("Speech model installed.")
            if not s.hosted and s.settings.voice_handsfree:
                voice_hud.set_handsfree(True, lang)
            st.rerun()
        except Exception as exc:  # network errors etc.
            st.error(f"Download failed: {exc}")
    return False


def _orb(active: bool) -> str:
    bars = "".join(f"<i style='animation-delay:{i * .07:.2f}s'></i>" for i in range(24))
    cap = "Processing…" if active else "Hands-free: just speak · or record a clip below"
    return C._clean(ORB.format(cls=" on" if active else "", bars=bars, cap=cap))


def render() -> None:
    s = state.svc()
    st.markdown(C.page_title("Voice Assistant", "Speak or type · offline speech · system answers · agent tasks",
                             "brain"), unsafe_allow_html=True)
    if nav := st.session_state.pop("voice_nav", None):
        st.switch_page(st.session_state.pages[nav])
    if op := st.session_state.pop("voice_confirm", None):
        confirm_dialog(op)
    voice_hud.page_section()

    left, right = st.columns([1, 1.25], gap="large")
    with left:
        codes = list(i18n.LANGS)
        _lang()
        st.selectbox("Assistant language", codes, key="voice_lang", on_change=_lang_changed,
                     format_func=lambda c: f"{i18n.LANGS[c]['name']} · {i18n.LANGS[c]['native']}"
                     + ("" if i18n.full_support(c) else "  (speech only, English replies)"))
        lang = _lang()
        if lang == "ur":
            st.caption("Urdu speech is recognised with the Hindustani model and shown in Urdu script; you can also "
                       "type in Urdu or Roman Urdu (e.g. “awaz barhao”, “battery kitni hai”).")
        elif not i18n.full_support(lang):
            st.caption("Speech recognition and voice work in this language; system commands are matched in English.")
        st.markdown(_orb(False), unsafe_allow_html=True)
        ready = _model_box()
        audio = st.audio_input("Speak a command", key="voice_mic", disabled=not ready, sample_rate=16000)
        if audio is not None:
            data = audio.getvalue()
            digest = hashlib.sha1(data).hexdigest()
            if st.session_state.get("voice_last_clip") != digest:
                st.session_state.voice_last_clip = digest
                with st.spinner("Recognising speech offline…"):
                    try:
                        text = stt.transcribe(data, s.voice_dir, _lang())
                    except Exception as exc:
                        text = ""
                        st.error(f"Speech recognition failed: {exc}")
                if text:
                    process(text, "voice")
                    st.rerun()
                else:
                    st.warning("I couldn't hear any words — try again, closer to the microphone.")
        with st.form("voice_text", clear_on_submit=True, border=False):
            c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
            typed = c1.text_input("Or type to the assistant", placeholder="e.g. what's using my memory?")
            if c2.form_submit_button("Send", type="primary", width="stretch") and typed:
                process(typed, "text")
                st.rerun()
        st.markdown("**Quick commands**")
        cols = st.columns(2)
        for i, q in enumerate(QUICK):
            if cols[i % 2].button(q, key=f"vq_{i}", width="stretch"):
                process(q, "quick")
                st.rerun()
        with st.expander("Voice settings", icon=":material/tune:"):
            st.toggle("Speak replies (offline voice)", value=True, key="voice_tts",
                      disabled=not tts.available(lang), help="Windows voices for English; bundled espeak-ng for all languages.")
            st.slider("Speech rate", -5, 5, 1, key="voice_rate")
            st.toggle("Open the Command Center for agent tasks", value=True, key="voice_auto_open")
            if not tts.available(lang):
                st.caption("No offline voice found on this server (install espeak-ng).")

    with right:
        hist = log()
        st.markdown(C.panel("Conversation", "terminal",
                            "" if hist else f"<div class='empty'>{C.esc(HELP)}</div>",
                            meta=f"{len(hist) // 2} exchange(s)"), unsafe_allow_html=True)
        box = st.container(height=520, border=False)
        with box:
            for m in hist[-40:]:
                with st.chat_message(m["role"], avatar=":material/person:" if m["role"] == "user"
                                     else ":material/smart_toy:"):
                    tag = f" · {m['src']}" if m.get("src") else (f" · {m['kind']}" if m.get("kind") else "")
                    st.markdown(f"<div dir='auto'>{C.esc(m['text'])}</div>", unsafe_allow_html=True)
                    if m.get("heard"):
                        st.caption(f"understood as: {m['heard']}")
                    st.caption(m["t"] + tag)
        if hist and st.button("Clear conversation", icon=":material/delete_sweep:"):
            st.session_state.voice_log = []
            st.rerun()
    st.caption("Privacy: speech is recognised offline by Vosk and replies are spoken by a local voice. Voice commands "
               "never run directly — risky actions need your click, and agent tasks go through the normal plan, "
               "policy and approval steps.")
